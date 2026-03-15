from __future__ import annotations

from typing import Any, Dict

from rest_framework import serializers
from rest_framework.exceptions import ValidationError

from crm.api.mixins import ContactAPIMixin
from crm.models import Contact
from crm.services.contact import normalize_phone_e164


class ContactCreateSerializer(ContactAPIMixin, serializers.ModelSerializer):
    name = serializers.CharField(required=False, allow_blank=True)
    whatsapp_name = serializers.CharField(required=False, allow_blank=True)
    type = serializers.JSONField(required=False)
    tags = serializers.JSONField(required=False)
    custom_fields = serializers.JSONField(required=False)
    activity_summary = serializers.JSONField(required=False)
    is_blacklisted = serializers.BooleanField(required=False)
    do_not_contact = serializers.BooleanField(required=False)

    class Meta:
        model = Contact
        fields = [
            "name",
            "fullname",
            "whatsapp_name",
            "email",
            "phone",
            "company",
            "source",
            "is_blacklisted",
            "do_not_contact",
            "type",
            "tags",
            "custom_fields",
            "activity_summary",
            "ctype",
        ]
        read_only_fields = ["ctype"]

    def validate(self, attrs: Dict[str, Any]) -> Dict[str, Any]:
        request = self.context.get("request")
        tenant = getattr(request, "tenant", None) or getattr(getattr(request, "user", None), "tenant", None)
        if tenant is None:
            raise ValidationError({"tenant": "User must belong to a tenant"})

        raw_name = attrs.get("name") or attrs.get("fullname") or attrs.get("whatsapp_name")
        name = str(raw_name).strip() if raw_name else ""
        if not name:
            raise ValidationError({"name": "name is required"})
        attrs["fullname"] = name

        contact_type, error = self._resolve_contact_type(tenant, attrs.get("type"))
        if error:
            raise ValidationError({"type": error})
        if contact_type is None:
            from crm.models import ContactType
            contact_type = ContactType.objects.filter(tenant=tenant, is_default=True).first()
        attrs["ctype"] = contact_type
        attrs.pop("type", None)

        try:
            attrs["tags"] = self._normalize_tags(attrs.get("tags")) if "tags" in attrs else []
            attrs["custom_fields"] = (
                self._normalize_custom_fields(attrs.get("custom_fields")) if "custom_fields" in attrs else {}
            )
            attrs["activity_summary"] = (
                self._normalize_activity_summary(attrs.get("activity_summary"))
                if "activity_summary" in attrs
                else {}
            )
        except ValueError as exc:
            raise ValidationError({"detail": str(exc)}) from exc

        attrs["email"] = attrs.get("email", "")
        raw_phone = attrs.get("phone", "")
        normalized_phone = normalize_phone_e164(raw_phone)
        attrs["phone"] = normalized_phone or raw_phone or ""
        attrs["company"] = attrs.get("company", "")
        attrs["source"] = attrs.get("source", "api")
        return attrs

    def create(self, validated_data: Dict[str, Any]) -> Contact:
        tags = validated_data.pop("tags", [])
        custom_fields = validated_data.pop("custom_fields", {})
        activity_summary = validated_data.pop("activity_summary", {})

        contact = Contact.objects.create(**validated_data)
        if self._apply_meta_updates(
            contact,
            tags=tags,
            custom_fields=custom_fields,
            activity_summary=activity_summary,
        ):
            contact.save(update_fields=["brief_facts"])
        return contact

    def to_representation(self, instance: Contact) -> Dict[str, Any]:
        return self._serialize_contact(instance)
