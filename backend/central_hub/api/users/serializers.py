from __future__ import annotations

from typing import Any, Dict, Optional

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.db import transaction
from rest_framework import serializers

from central_hub.capabilities import get_effective_capabilities
from central_hub.rbac import ROLE_ORDER, _user_group_names

UserModel = get_user_model()


def _resolve_role(user) -> str:
    """
    Return the highest RBAC role for the user based on Group membership.

    Falls back to "member" when no role group is present.
    """
    if getattr(user, "is_superuser", False):
        return "platform_admin"

    groups = {name.lower() for name in _user_group_names(user)}
    best_rank = -1
    best_role = None
    for idx, role in enumerate(ROLE_ORDER):
        if role in groups:
            best_rank = idx
            best_role = role
    return best_role or "member"


def _set_role_groups(user, role: str) -> None:
    role_lc = (role or "").lower().strip()
    if role_lc not in ROLE_ORDER:
        raise serializers.ValidationError({"role": "Invalid role"})

    # Remove existing role groups (keep non-role groups intact).
    existing = list(user.groups.all())
    for g in existing:
        if g.name.lower() in ROLE_ORDER:
            user.groups.remove(g)

    group, _ = Group.objects.get_or_create(name=role_lc)
    user.groups.add(group)


class MoioUserReadSerializer(serializers.ModelSerializer):
    full_name = serializers.SerializerMethodField()
    avatar_url = serializers.SerializerMethodField()
    organization = serializers.SerializerMethodField()
    role = serializers.SerializerMethodField()
    groups = serializers.SerializerMethodField()
    reports_to_ids = serializers.PrimaryKeyRelatedField(many=True, read_only=True, source="reports_to")

    class Meta:
        model = UserModel
        fields = (
            "id",
            "email",
            "username",
            "first_name",
            "last_name",
            "full_name",
            "phone",
            "avatar_url",
            "is_active",
            "is_staff",
            "is_superuser",
            "role",
            "groups",
            "organization",
            "reports_to_ids",
            "last_login",
            "created",
        )

    def get_full_name(self, obj: UserModel) -> str:
        full_name = f"{obj.first_name} {obj.last_name}".strip()
        return full_name or obj.username

    def get_avatar_url(self, obj: UserModel) -> Optional[str]:
        if not getattr(obj, "avatar", None):
            return None
        request = self.context.get("request")
        try:
            url = obj.avatar.url
        except Exception:
            return None
        if request:
            return request.build_absolute_uri(url)
        return url

    def get_organization(self, obj: UserModel) -> Optional[Dict[str, Any]]:
        tenant = getattr(obj, "tenant", None)
        if not tenant:
            return None
        return {
            "id": str(tenant.pk),
            "name": getattr(tenant, "nombre", str(tenant.pk)),
            "domain": str(getattr(tenant, "domain", "") or ""),
            "subdomain": str(getattr(tenant, "subdomain", "") or ""),
            "primary_domain": str(getattr(tenant, "primary_domain", "") or ""),
            "schema_name": str(getattr(tenant, "schema_name", "") or ""),
        }

    def get_role(self, obj: UserModel) -> str:
        return _resolve_role(obj)

    def get_groups(self, obj: UserModel) -> list[str]:
        return sorted(set(_user_group_names(obj)))


class MoioUserWriteSerializer(serializers.ModelSerializer):
    """
    Input serializer for creating/updating users in a tenant.

    Notes:
    - `tenant` is always forced to the request user's tenant.
    - `role` is implemented via Django Group membership (see `central_hub.rbac`).
    """

    role = serializers.ChoiceField(choices=tuple(ROLE_ORDER), required=False)
    password = serializers.CharField(write_only=True, required=False, allow_blank=False, trim_whitespace=False)
    reports_to_ids = serializers.PrimaryKeyRelatedField(
        many=True,
        queryset=UserModel.objects.none(),
        required=False,
        source="reports_to",
    )

    class Meta:
        model = UserModel
        fields = (
            "email",
            "username",
            "first_name",
            "last_name",
            "phone",
            "is_active",
            "role",
            "reports_to_ids",
            "password",
        )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if "request" in self.context:
            tenant = getattr(self.context["request"].user, "tenant", None)
            if tenant:
                self.fields["reports_to_ids"].queryset = UserModel.objects.filter(tenant=tenant)

    def validate_role(self, value: str) -> str:
        role = (value or "").lower().strip()
        # Only superusers can grant platform_admin.
        request = self.context.get("request")
        if role == "platform_admin" and not getattr(getattr(request, "user", None), "is_superuser", False):
            raise serializers.ValidationError("Only platform admins can assign platform_admin role")
        return role

    def validate(self, attrs: Dict[str, Any]) -> Dict[str, Any]:
        if self.instance is None:
            if not attrs.get("password"):
                raise serializers.ValidationError({"password": "Password is required"})
        return attrs

    def create(self, validated_data: Dict[str, Any]):
        request = self.context.get("request")
        actor = getattr(request, "user", None)
        tenant = getattr(actor, "tenant", None)
        if tenant is None:
            raise serializers.ValidationError({"tenant": "Authenticated user must belong to a tenant"})

        eff = get_effective_capabilities(actor, tenant)
        seats_limit = eff.limits.get("seats")
        if seats_limit is not None:
            current_count = UserModel.objects.filter(tenant=tenant, is_active=True).count()
            if current_count >= seats_limit:
                raise serializers.ValidationError(
                    {"seats": f"User limit reached ({seats_limit} users). Upgrade your plan to add more users."}
                )

        role = validated_data.pop("role", None)
        password = validated_data.pop("password", None)
        reports_to = validated_data.pop("reports_to", None)
        with transaction.atomic():
            user = UserModel.objects.create_user(
                tenant=tenant,
                password=password,
                **validated_data,
            )
            if role:
                _set_role_groups(user, role)
            if reports_to is not None:
                user.reports_to.set(reports_to)
        return user

    def update(self, instance, validated_data: Dict[str, Any]):
        role = validated_data.pop("role", None)
        password = validated_data.pop("password", None)
        reports_to = validated_data.pop("reports_to", None)

        for field, value in validated_data.items():
            setattr(instance, field, value)

        if password:
            instance.set_password(password)

        with transaction.atomic():
            instance.save()
            if role:
                _set_role_groups(instance, role)
            if reports_to is not None:
                instance.reports_to.set(reports_to)

        return instance
