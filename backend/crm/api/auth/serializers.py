from __future__ import annotations

from typing import Any, Dict

from django.contrib.auth import get_user_model
from rest_framework import serializers

from crm.api.settings.preferences import build_user_preferences
from central_hub.rbac import ROLE_ORDER, _role_rank, _user_group_names
from central_hub.tenant_config import get_tenant_config

UserModel = get_user_model()


class UserSerializer(serializers.ModelSerializer):
    full_name = serializers.SerializerMethodField()
    role = serializers.SerializerMethodField()
    avatar_url = serializers.SerializerMethodField()
    organization = serializers.SerializerMethodField()
    preferences = serializers.SerializerMethodField()

    class Meta:
        model = UserModel
        fields = (
            "id",
            "username",
            "email",
            "full_name",
            "role",
            "avatar_url",
            "organization",
            "preferences",
        )

    def get_full_name(self, obj: UserModel) -> str:
        full_name = f"{obj.first_name} {obj.last_name}".strip()
        return full_name or obj.username

    def get_role(self, obj: UserModel) -> str:
        if obj.is_superuser:
            return "platform_admin"

        highest_rank = max((_role_rank(name) for name in _user_group_names(obj)), default=-1)
        if highest_rank >= 0:
            return ROLE_ORDER[highest_rank]

        if obj.is_staff:
            return "manager"

        return "member"

    def get_avatar_url(self, obj: UserModel) -> str | None:
        if not obj.avatar:
            return None
        request = self.context.get("request")
        try:
            url = obj.avatar.url
        except ValueError:
            return None
        if request:
            return request.build_absolute_uri(url)
        return url

    def get_organization(self, obj: UserModel) -> Dict[str, Any] | None:
        tenant = getattr(obj, "tenant", None)
        if not tenant:
            return None
        return {
            "id": str(tenant.pk),
            "name": tenant.nombre,
            "domain": str(getattr(tenant, "domain", "") or ""),
            "subdomain": str(getattr(tenant, "subdomain", "") or ""),
            "primary_domain": str(getattr(tenant, "primary_domain", "") or ""),
            "schema_name": str(getattr(tenant, "schema_name", "") or ""),
        }

    def get_preferences(self, obj: UserModel) -> Dict[str, Any]:
        tenant = getattr(obj, "tenant", None)
        config = get_tenant_config(tenant) if tenant else None
        return build_user_preferences(obj, config)
