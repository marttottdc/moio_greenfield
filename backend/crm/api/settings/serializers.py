from __future__ import annotations

from typing import Any, Dict, Type

from django.urls import reverse
from rest_framework import serializers

from chatbot.models.agent_configuration import AgentConfiguration
from crm.models import WebhookConfig
from central_hub.models import TenantConfiguration
from central_hub.webhooks.utils import available_handlers


class BaseTenantConfigurationSerializer(serializers.ModelSerializer):
    class Meta:
        model = TenantConfiguration
        fields: tuple[str, ...] = ()


class OpenAISettingsSerializer(BaseTenantConfigurationSerializer):
    class Meta(BaseTenantConfigurationSerializer.Meta):
        fields = (
            "openai_integration_enabled",
            "openai_api_key",
            "openai_max_retries",
            "openai_default_model",
            "openai_embedding_model",
        )


class WhatsAppSettingsSerializer(BaseTenantConfigurationSerializer):
    class Meta(BaseTenantConfigurationSerializer.Meta):
        fields = (
            "whatsapp_integration_enabled",
            "whatsapp_token",
            "whatsapp_url",
            "whatsapp_phone_id",
            "whatsapp_business_account_id",
            "whatsapp_name",
            "whatsapp_catalog_id",
        )


class SMTPSettingsSerializer(BaseTenantConfigurationSerializer):
    class Meta(BaseTenantConfigurationSerializer.Meta):
        fields = (
            "smtp_integration_enabled",
            "smtp_host",
            "smtp_port",
            "smtp_use_tls",
            "smtp_user",
            "smtp_password",
            "smtp_from",
        )


class MercadoPagoSettingsSerializer(BaseTenantConfigurationSerializer):
    class Meta(BaseTenantConfigurationSerializer.Meta):
        fields = (
            "mercadopago_integration_enabled",
            "mercadopago_webhook_secret",
            "mercadopago_public_key",
            "mercadopago_access_token",
            "mercadopago_client_id",
            "mercadopago_client_secret",
        )


class DACSettingsSerializer(BaseTenantConfigurationSerializer):
    class Meta(BaseTenantConfigurationSerializer.Meta):
        fields = (
            "dac_integration_enabled",
            "dac_user",
            "dac_password",
            "dac_rut",
            "dac_sender_name",
            "dac_sender_phone",
            "dac_base_url",
            "dac_notification_list",
            "dac_tracking_period",
            "dac_polling_interval",
        )


class AssistantsSettingsSerializer(BaseTenantConfigurationSerializer):
    class Meta(BaseTenantConfigurationSerializer.Meta):
        fields = (
            "assistants_enabled",
            "assistants_default_id",
            "conversation_handler",
            "assistant_smart_reply_enabled",
            "assistant_output_formatting_instructions",
            "assistant_output_schema",
            "assistants_inactivity_limit",
            "chatbot_enabled",
            "default_agent_id",
        )


class HandoffAgentSerializer(serializers.Serializer):
    """Serializes handoff agents with their essential info."""
    id = serializers.UUIDField(read_only=True)
    name = serializers.CharField(read_only=True)
    model = serializers.CharField(read_only=True)


class AgentConfigurationSerializer(serializers.ModelSerializer):
    handoffs = HandoffAgentSerializer(many=True, read_only=True)
    handoff_ids = serializers.ListField(
        child=serializers.UUIDField(),
        write_only=True,
        required=False,
        help_text="List of agent IDs to set as handoff targets"
    )

    class Meta:
        model = AgentConfiguration
        fields = (
            "id",
            "enabled",
            "name",
            "model",
            "instructions",
            "channel",
            "channel_id",
            "tools",
            "default",
            "model_settings",
            "handoff_description",
            "guardrails",
            "output",
            "run_behavior",
            "handoffs",
            "handoff_ids",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("id", "created_at", "updated_at", "handoffs")

    def create(self, validated_data: Dict[str, Any]) -> AgentConfiguration:
        handoff_ids = validated_data.pop("handoff_ids", None)
        instance = super().create(validated_data)
        if handoff_ids is not None:
            self._set_handoffs(instance, handoff_ids)
        return instance

    def update(self, instance: AgentConfiguration, validated_data: Dict[str, Any]) -> AgentConfiguration:
        handoff_ids = validated_data.pop("handoff_ids", None)
        instance = super().update(instance, validated_data)
        if handoff_ids is not None:
            self._set_handoffs(instance, handoff_ids)
        return instance

    def _set_handoffs(self, instance: AgentConfiguration, agent_ids: list) -> None:
        """Set the handoff agents for this agent."""
        handoff_agents = AgentConfiguration.objects.filter(
            id__in=agent_ids,
            tenant=instance.tenant
        )
        instance.handoffs.set(handoff_agents)


class LinkedFlowSerializer(serializers.Serializer):
    id = serializers.UUIDField(read_only=True)
    name = serializers.CharField(read_only=True)
    status = serializers.CharField(read_only=True)
    is_enabled = serializers.BooleanField(read_only=True)


class WebhookConfigSerializer(serializers.ModelSerializer):
    linked_flows = LinkedFlowSerializer(many=True, read_only=True)
    linked_flow_ids = serializers.ListField(
        child=serializers.UUIDField(),
        write_only=True,
        required=False,
        help_text="List of flow IDs to link to this webhook"
    )

    class Meta:
        model = WebhookConfig
        fields = (
            "id",
            "name",
            "description",
            "expected_schema",
            "expected_content_type",
            "expected_origin",
            "auth_type",
            "auth_config",
            "handler_path",
            "url",
            "locked",
            "linked_flows",
            "linked_flow_ids",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("id", "created_at", "updated_at", "linked_flows")

    def to_representation(self, instance: WebhookConfig) -> dict[str, Any]:
        data = super().to_representation(instance)
        if not data.get("url"):
            request = self.context.get("request") if hasattr(self, "context") else None
            if request is not None:
                try:
                    computed_url = request.build_absolute_uri(
                        reverse("generic_webhook_receiver", args=[instance.id])
                    )
                except Exception:
                    computed_url = ""
                if computed_url:
                    data["url"] = computed_url
        return data

    def validate_handler_path(self, value: str) -> str:
        if not value:
            return value
        handlers = available_handlers()
        if value not in handlers:
            raise serializers.ValidationError("Unknown webhook handler")
        return value

    def validate(self, attrs: Dict[str, Any]) -> Dict[str, Any]:
        auth_type = attrs.get("auth_type")
        if not auth_type and self.instance:
            auth_type = self.instance.auth_type

        auth_config = attrs.get("auth_config")
        if auth_config is None and self.instance:
            auth_config = self.instance.auth_config

        errors: Dict[str, Any] = {}

        if auth_type == WebhookConfig.AuthType.BASIC:
            if not auth_config or not all(key in auth_config for key in ("username", "password")):
                errors["auth_config"] = "Basic auth requires 'username' and 'password'"
        elif auth_type == WebhookConfig.AuthType.BEARER_TOKEN:
            if not auth_config or "token" not in auth_config:
                errors["auth_config"] = "Bearer auth requires 'token'"
        elif auth_type == WebhookConfig.AuthType.HMAC_SHA256:
            if not auth_config or "secret" not in auth_config:
                errors["auth_config"] = "HMAC auth requires 'secret'"
        elif auth_type == WebhookConfig.AuthType.CUSTOM_HEADER:
            if not auth_config or not all(key in auth_config for key in ("header", "value")):
                errors["auth_config"] = "Header auth requires 'header' and 'value'"
        elif auth_type == WebhookConfig.AuthType.QUERY_PARAM:
            if not auth_config or not all(key in auth_config for key in ("param", "value")):
                errors["auth_config"] = "Query auth requires 'param' and 'value'"
        elif auth_type == WebhookConfig.AuthType.JWT:
            if not auth_config or not (auth_config.get("secret") or auth_config.get("jwks_url")):
                errors["auth_config"] = "JWT auth requires 'secret' or 'jwks_url'"

        if errors:
            raise serializers.ValidationError(errors)

        return attrs

    def create(self, validated_data: Dict[str, Any]) -> WebhookConfig:
        linked_flow_ids = validated_data.pop("linked_flow_ids", None)
        instance = super().create(validated_data)
        if linked_flow_ids is not None:
            self._set_linked_flows(instance, linked_flow_ids)
        return instance

    def update(self, instance: WebhookConfig, validated_data: Dict[str, Any]) -> WebhookConfig:
        linked_flow_ids = validated_data.pop("linked_flow_ids", None)
        instance = super().update(instance, validated_data)
        if linked_flow_ids is not None:
            self._set_linked_flows(instance, linked_flow_ids)
        return instance

    def _set_linked_flows(self, instance: WebhookConfig, flow_ids: list) -> None:
        from flows.models import Flow
        tenant = instance.tenant
        flows = Flow.objects.filter(id__in=flow_ids, tenant=tenant)
        instance.linked_flows.set(flows)


INTEGRATION_SERIALIZERS: Dict[str, Type[BaseTenantConfigurationSerializer]] = {
    "openai": OpenAISettingsSerializer,
    "whatsapp": WhatsAppSettingsSerializer,
    "smtp": SMTPSettingsSerializer,
    "mercadopago": MercadoPagoSettingsSerializer,
    "dac": DACSettingsSerializer,
    "assistants": AssistantsSettingsSerializer,
}


class NotificationPreferenceSerializer(serializers.Serializer):
    email = serializers.BooleanField(required=False)
    push = serializers.BooleanField(required=False)
    desktop = serializers.BooleanField(required=False)


class PreferenceUpdateSerializer(serializers.Serializer):
    theme = serializers.ChoiceField(choices=("light", "dark"), required=False)
    language = serializers.ChoiceField(choices=("en", "es"), required=False)
    timezone = serializers.CharField(required=False)
    notifications = NotificationPreferenceSerializer(required=False)
    dashboard_layout = serializers.ChoiceField(choices=("compact", "expanded"), required=False)
