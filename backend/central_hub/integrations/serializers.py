"""
IntegrationConfig Serializers

Provides dynamic serialization with schema-based validation from the registry.
Supports both generic serialization and per-integration field validation.
"""

from __future__ import annotations

from typing import Any

from rest_framework import serializers
from drf_spectacular.utils import extend_schema_field
from drf_spectacular.types import OpenApiTypes

from central_hub.integrations.models import IntegrationConfig
from central_hub.integrations.registry import (
    INTEGRATION_REGISTRY,
    get_integration,
    get_sensitive_fields,
    validate_integration_config,
)


class IntegrationConfigSerializer(serializers.ModelSerializer):
    """
    Serializer for IntegrationConfig with dynamic validation.
    
    Masks sensitive fields in responses and validates config
    against the registered schema for the integration type.
    """
    
    integration_name = serializers.SerializerMethodField()
    integration_category = serializers.SerializerMethodField()
    is_configured = serializers.SerializerMethodField()
    supports_multi_instance = serializers.SerializerMethodField()
    available_models = serializers.SerializerMethodField()
    
    class Meta:
        model = IntegrationConfig
        fields = (
            "id",
            "slug",
            "instance_id",
            "name",
            "enabled",
            "config",
            "metadata",
            "integration_name",
            "integration_category",
            "is_configured",
            "supports_multi_instance",
            "available_models",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("id", "created_at", "updated_at")
    
    @extend_schema_field(OpenApiTypes.STR)
    def get_integration_name(self, obj: IntegrationConfig) -> str:
        """Get human-readable integration name from registry."""
        definition = get_integration(obj.slug)
        return definition.name if definition else obj.slug
    
    @extend_schema_field(OpenApiTypes.STR)
    def get_integration_category(self, obj: IntegrationConfig) -> str:
        """Get integration category from registry."""
        definition = get_integration(obj.slug)
        return definition.category if definition else "other"
    
    @extend_schema_field(OpenApiTypes.BOOL)
    def get_is_configured(self, obj: IntegrationConfig) -> bool:
        """Check if required fields are configured."""
        return obj.is_configured()
    
    @extend_schema_field(OpenApiTypes.BOOL)
    def get_supports_multi_instance(self, obj: IntegrationConfig) -> bool:
        """Check if this integration supports multiple instances."""
        definition = get_integration(obj.slug)
        return definition.supports_multi_instance if definition else False
    
    def get_available_models(self, obj: IntegrationConfig) -> list[dict[str, str]] | None:
        """Get available models for OpenAI integration."""
        if obj.slug != "openai":
            return None
        
        if not obj.is_configured():
            return None
        
        api_key = obj.config.get("api_key")
        if not api_key:
            return None
        
        from django.core.cache import cache
        import logging
        logger = logging.getLogger(__name__)
        
        cache_key = f"openai_models_{obj.tenant_id}"
        cached_models = cache.get(cache_key)
        if cached_models is not None:
            return cached_models
        
        try:
            from openai import OpenAI
            client = OpenAI(api_key=api_key)
            models_response = client.models.list()
            
            models = [
                {"id": model.id, "created": model.created}
                for model in models_response.data
            ]
            
            cache.set(cache_key, models, 3600)
            return models
        except Exception as e:
            import logging
            logging.getLogger(__name__).error(f"Failed to fetch OpenAI models: {e}")
            return None
    
    def to_representation(self, instance: IntegrationConfig) -> dict[str, Any]:
        """Mask sensitive fields in the response."""
        data = super().to_representation(instance)
        
        sensitive_fields = get_sensitive_fields(instance.slug)
        config = data.get("config", {})
        
        for field in sensitive_fields:
            if field in config and config[field]:
                value = config[field]
                if isinstance(value, str) and len(value) > 8:
                    config[field] = value[:4] + "****" + value[-4:]
                else:
                    config[field] = "****"
        
        data["config"] = config
        return data
    
    def validate_slug(self, value: str) -> str:
        """Validate that slug is a known integration type."""
        if value not in INTEGRATION_REGISTRY:
            raise serializers.ValidationError(
                f"Unknown integration type: {value}. "
                f"Valid types: {', '.join(INTEGRATION_REGISTRY.keys())}"
            )
        return value
    
    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        """Validate config against the integration schema."""
        slug = attrs.get("slug") or (self.instance.slug if self.instance else None)
        config = attrs.get("config", {})
        
        if slug and config:
            errors = validate_integration_config(slug, config)
            if errors:
                raise serializers.ValidationError({"config": errors})
        
        return attrs


class IntegrationConfigCreateSerializer(IntegrationConfigSerializer):
    """Serializer for creating new integration configs."""
    
    class Meta(IntegrationConfigSerializer.Meta):
        read_only_fields = ("id", "created_at", "updated_at")
    
    def create(self, validated_data: dict[str, Any]) -> IntegrationConfig:
        """Create integration config with tenant from request."""
        request = self.context.get("request")
        if request and hasattr(request, "user") and hasattr(request.user, "tenant"):
            validated_data["tenant"] = request.user.tenant
        return super().create(validated_data)


class IntegrationConfigUpdateSerializer(IntegrationConfigSerializer):
    """Serializer for updating integration configs (partial updates)."""
    
    class Meta(IntegrationConfigSerializer.Meta):
        read_only_fields = ("id", "slug", "tenant", "created_at", "updated_at")
    
    def update(
        self, instance: IntegrationConfig, validated_data: dict[str, Any]
    ) -> IntegrationConfig:
        """Merge config updates. Skip sensitive fields with masked values (e.g. sk-****xyz)."""
        if "config" in validated_data:
            new_config = validated_data.pop("config")
            sensitive_fields = get_sensitive_fields(instance.slug)
            updated_config = dict(instance.config)
            for key, value in new_config.items():
                if key in sensitive_fields and self._looks_like_mask(value):
                    continue
                updated_config[key] = value
            instance.config = updated_config
        if instance.is_configured() and not instance.enabled:
            validated_data["enabled"] = True
        return super().update(instance, validated_data)

    @staticmethod
    def _looks_like_mask(value: Any) -> bool:
        """Return True if value looks like a masked placeholder (should not overwrite real secret)."""
        if not isinstance(value, str) or not value:
            return True
        return "****" in value


class IntegrationListSerializer(serializers.Serializer):
    """Serializer for listing available integration types from registry."""
    
    slug = serializers.CharField()
    name = serializers.CharField()
    description = serializers.CharField()
    category = serializers.CharField()
    icon = serializers.CharField()
    supports_multi_instance = serializers.BooleanField()
    is_configured = serializers.BooleanField(default=False)
    enabled = serializers.BooleanField(default=False)
    instance_count = serializers.IntegerField(default=0)


class IntegrationSchemaSerializer(serializers.Serializer):
    """Serializer for integration schema/field definitions."""
    
    slug = serializers.CharField()
    name = serializers.CharField()
    description = serializers.CharField()
    category = serializers.CharField()
    fields = serializers.ListField(child=serializers.DictField())
    required_fields = serializers.ListField(child=serializers.CharField())
    sensitive_fields = serializers.ListField(child=serializers.CharField())
