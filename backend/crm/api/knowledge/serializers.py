from __future__ import annotations

from typing import Any, Dict

from rest_framework import serializers

from crm.models import KnowledgeItem


class KnowledgeItemSerializer(serializers.ModelSerializer):
    data = serializers.JSONField(required=False, default=dict)

    class Meta:
        model = KnowledgeItem
        fields = [
            "id",
            "title",
            "description",
            "url",
            "type",
            "category",
            "visibility",
            "slug",
            "data",
            "created",
            "modified",
        ]
        read_only_fields = ["id", "created", "modified", "tenant"]

    def validate_title(self, value: str) -> str:
        if not value or not value.strip():
            raise serializers.ValidationError("Title is required")
        return value.strip()

    def validate(self, attrs: Dict[str, Any]) -> Dict[str, Any]:
        attrs.pop("tenant", None)
        attrs.pop("tenant_id", None)
        return attrs

    def create(self, validated_data: Dict[str, Any]) -> KnowledgeItem:
        request = self.context.get("request")
        tenant = getattr(getattr(request, "user", None), "tenant", None)
        if tenant is None:
            raise serializers.ValidationError({"tenant": "User must belong to a tenant"})
        validated_data["tenant"] = tenant
        return super().create(validated_data)

    def update(self, instance: KnowledgeItem, validated_data: Dict[str, Any]) -> KnowledgeItem:
        validated_data.pop("tenant", None)
        validated_data.pop("tenant_id", None)
        return super().update(instance, validated_data)

    def to_representation(self, instance: KnowledgeItem) -> Dict[str, Any]:
        data = super().to_representation(instance)
        data["created"] = instance.created.isoformat() if instance.created else None
        data["modified"] = instance.modified.isoformat() if instance.modified else None
        return data
