"""
Tenant config adapter: reads from IntegrationConfig + Tenant.

Replaces TenantConfiguration. Integration config lives in IntegrationConfig;
organization defaults (locale, currency, assistants) live on Tenant.
"""
from __future__ import annotations

from types import SimpleNamespace
from typing import TYPE_CHECKING, Any, Iterator

if TYPE_CHECKING:
    from tenancy.models import Tenant


def get_tenant_config(tenant: "Tenant") -> SimpleNamespace:
    """
    Return a config object with the same attribute interface as TenantConfiguration.

    Reads from IntegrationConfig (integrations) and Tenant (org fields).
    """
    from central_hub.integrations.models import IntegrationConfig
    from central_hub.integrations.registry import (
        INTEGRATION_REGISTRY,
        get_new_to_legacy_mapping,
    )

    # Build attrs from IntegrationConfig
    attrs: dict[str, Any] = {}
    for slug, definition in INTEGRATION_REGISTRY.items():
        enabled_field = definition.enabled_field_legacy
        if enabled_field:
            attrs[enabled_field] = False

        for f in definition.fields:
            if f.legacy_field:
                attrs[f.legacy_field] = f.default if f.default is not None else ""

    # Populate from IntegrationConfig
    for slug, definition in INTEGRATION_REGISTRY.items():
        cfg = IntegrationConfig.get_for_tenant(tenant, slug, "default")
        if cfg:
            if definition.enabled_field_legacy:
                attrs[definition.enabled_field_legacy] = cfg.enabled
            mapping = get_new_to_legacy_mapping(slug)
            for new_key, legacy_key in mapping.items():
                if new_key in cfg.config and cfg.config[new_key] is not None:
                    attrs[legacy_key] = cfg.config[new_key]

    # Org-level fields from Tenant
    attrs["organization_locale"] = getattr(tenant, "organization_locale", None) or "en"
    attrs["organization_currency"] = getattr(tenant, "organization_currency", None) or "USD"
    attrs["organization_timezone"] = getattr(tenant, "organization_timezone", None) or "UTC"
    attrs["organization_date_format"] = getattr(tenant, "organization_date_format", None) or "DD/MM/YYYY"
    attrs["organization_time_format"] = getattr(tenant, "organization_time_format", None) or "24h"
    attrs["default_notification_list"] = getattr(tenant, "default_notification_list", None) or ""

    # Chatbot/assistant/agent settings from chatbot app
    from chatbot.models.tenant_chatbot_settings import TenantChatbotSettings
    s, _ = TenantChatbotSettings.objects.get_or_create(tenant=tenant)
    attrs["assistants_enabled"] = s.assistants_enabled
    attrs["assistants_default_id"] = s.assistants_default_id or ""
    attrs["conversation_handler"] = s.conversation_handler or "assistant"
    attrs["assistant_smart_reply_enabled"] = s.assistant_smart_reply_enabled
    attrs["assistant_output_formatting_instructions"] = s.assistant_output_formatting_instructions or ""
    attrs["assistant_output_schema"] = s.assistant_output_schema or ""
    attrs["assistants_inactivity_limit"] = s.assistants_inactivity_limit or 30
    attrs["chatbot_enabled"] = s.chatbot_enabled
    attrs["default_agent_id"] = s.default_agent_id or ""
    attrs["agent_allow_reopen_session"] = s.agent_allow_reopen_session
    attrs["agent_reopen_threshold"] = s.agent_reopen_threshold or 360

    attrs["tenant"] = tenant
    attrs["tenant_id"] = tenant.pk

    return SimpleNamespace(**attrs)


def get_tenant_config_by_id(tenant_id: int) -> SimpleNamespace:
    """Get config for tenant by ID. Resolves tenant then calls get_tenant_config."""
    from tenancy.models import Tenant
    tenant = Tenant.objects.get(pk=tenant_id)
    return get_tenant_config(tenant)


def iter_configs_with_integration_enabled(slug: str) -> Iterator[tuple["Tenant", SimpleNamespace]]:
    """Yield (tenant, config) for each tenant that has the given integration enabled."""
    from central_hub.integrations.models import IntegrationConfig
    for cfg in IntegrationConfig._base_manager.filter(slug=slug, enabled=True).select_related("tenant"):
        yield cfg.tenant, get_tenant_config(cfg.tenant)


def get_tenant_config_by_whatsapp_ids(waba_id: str, phone_id: str) -> SimpleNamespace | None:
    """
    Find config for tenant that has WhatsApp integration with matching business_account_id and phone_id.
    Returns None if not found. Raises ValueError if multiple tenants match (ambiguous).
    """
    from central_hub.integrations.models import IntegrationConfig
    matches = [
        cfg
        for cfg in IntegrationConfig.objects.filter(slug="whatsapp", enabled=True).select_related("tenant")
        if cfg.config.get("business_account_id") == waba_id and cfg.config.get("phone_id") == phone_id
    ]
    if not matches:
        return None
    if len(matches) > 1:
        raise ValueError("Configuration error: WABA ID present in multiple tenants")
    return get_tenant_config(matches[0].tenant)
