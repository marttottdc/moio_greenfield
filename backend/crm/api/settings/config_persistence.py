"""
Persistence helpers for integration config and org settings.

Maps between legacy TenantConfiguration field names and IntegrationConfig / Tenant.
"""
from __future__ import annotations

from typing import Any

from tenancy.models import Tenant


# URL integration slug -> IntegrationConfig slug (when they differ)
INTEGRATION_TO_CONFIG_SLUG: dict[str, str] = {
    "gmail": "smtp",
}


def _config_slug(integration_slug: str) -> str:
    """Resolve IntegrationConfig slug from URL integration slug."""
    return INTEGRATION_TO_CONFIG_SLUG.get(integration_slug, integration_slug)


def persist_integration_config(
    tenant: Tenant,
    integration_slug: str,
    validated_data: dict[str, Any],
    enabled: bool | None = None,
) -> None:
    """
    Persist integration config from validated serializer data to IntegrationConfig.

    Maps legacy field names (e.g. openai_api_key) to new config keys (e.g. api_key).
    """
    from central_hub.integrations.models import IntegrationConfig
    from central_hub.integrations.registry import (
        get_integration,
        get_legacy_to_new_mapping,
    )

    slug = _config_slug(integration_slug)
    definition = get_integration(slug)
    if not definition:
        return

    mapping = get_legacy_to_new_mapping(slug)
    config_data: dict[str, Any] = {}
    new_enabled = enabled

    for legacy_key, new_key in mapping.items():
        if legacy_key in validated_data:
            config_data[new_key] = validated_data[legacy_key]
    if definition.enabled_field_legacy and definition.enabled_field_legacy in validated_data:
        new_enabled = validated_data[definition.enabled_field_legacy]

    cfg, created = IntegrationConfig.get_or_create_for_tenant(
        tenant=tenant,
        slug=slug,
        instance_id="default",
        defaults={"config": {}, "enabled": False},
    )
    cfg.config.update(config_data)
    if new_enabled is not None:
        cfg.enabled = new_enabled
    cfg.save(update_fields=["config", "enabled", "updated_at"])


def disable_integration(tenant: Tenant, integration_slug: str) -> None:
    """Set integration enabled=False in IntegrationConfig."""
    from central_hub.integrations.models import IntegrationConfig

    slug = _config_slug(integration_slug)
    cfg = IntegrationConfig.get_for_tenant(tenant, slug, "default")
    if cfg:
        cfg.enabled = False
        cfg.save(update_fields=["enabled", "updated_at"])


def persist_org_settings(tenant: Tenant, validated_data: dict[str, Any]) -> None:
    """
    Persist org-level settings to Tenant and chatbot settings to TenantChatbotSettings.

    Org fields: organization_locale, currency, timezone, date_format, time_format,
    default_notification_list.
    Chatbot fields: assistants_enabled, conversation_handler, etc. (in chatbot app).
    """
    from chatbot.models.tenant_chatbot_settings import TenantChatbotSettings

    org_field_map = {
        "organization_locale": "organization_locale",
        "organization_currency": "organization_currency",
        "organization_timezone": "organization_timezone",
        "organization_date_format": "organization_date_format",
        "organization_time_format": "organization_time_format",
        "default_notification_list": "default_notification_list",
    }
    chatbot_field_map = {
        "assistants_enabled": "assistants_enabled",
        "assistants_default_id": "assistants_default_id",
        "conversation_handler": "conversation_handler",
        "assistant_smart_reply_enabled": "assistant_smart_reply_enabled",
        "assistant_output_formatting_instructions": "assistant_output_formatting_instructions",
        "assistant_output_schema": "assistant_output_schema",
        "assistants_inactivity_limit": "assistants_inactivity_limit",
        "chatbot_enabled": "chatbot_enabled",
        "default_agent_id": "default_agent_id",
        "agent_allow_reopen_session": "agent_allow_reopen_session",
        "agent_reopen_threshold": "agent_reopen_threshold",
    }

    org_updated = False
    for key in org_field_map:
        if key in validated_data:
            setattr(tenant, org_field_map[key], validated_data[key])
            org_updated = True
    if org_updated:
        tenant.save()

    chatbot_updated = False
    try:
        settings = tenant.chatbot_settings
    except TenantChatbotSettings.DoesNotExist:
        settings = TenantChatbotSettings.objects.create(tenant=tenant)
    for key in chatbot_field_map:
        if key in validated_data:
            setattr(settings, chatbot_field_map[key], validated_data[key])
            chatbot_updated = True
    if chatbot_updated:
        settings.save()
