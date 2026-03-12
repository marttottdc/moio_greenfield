"""
Integration Registry

Central registry for all integration types with their schemas, field mappings,
and validation rules. New integrations can be added here without database migrations.

The registry maps:
- slug → schema definition (fields, types, required fields)
- slug → legacy TenantConfiguration field mapping (for sync)
- slug → metadata (name, description, category)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable


@dataclass
class IntegrationField:
    """Definition of a single integration configuration field."""
    name: str
    field_type: str = "string"
    required: bool = False
    sensitive: bool = False
    default: Any = None
    description: str = ""
    legacy_field: str | None = None
    choices: list[tuple[str, str]] | None = None


@dataclass
class IntegrationDefinition:
    """
    Complete definition of an integration type (Integrations Hub contract).

    Identity: slug, name, category, supports_multi_instance
    Auth model: auth_scope = global | tenant | user
    Transport: supports_webhook, supports_oauth, supports_polling
    Runtime: adapter_module (dotted path to adapter class), webhook_path_suffix
    """
    slug: str
    name: str
    description: str
    category: str
    fields: list[IntegrationField] = field(default_factory=list)
    enabled_field_legacy: str | None = None
    supports_multi_instance: bool = False
    icon: str = ""
    docs_url: str = ""
    # Hub contract: auth and transport
    auth_scope: str = "tenant"  # "global" | "tenant" | "user"
    supports_webhook: bool = False
    supports_oauth: bool = False
    supports_polling: bool = False
    webhook_path_suffix: str = ""  # e.g. "shopify" -> .../shopify/webhook/
    adapter_module: str = ""  # e.g. "central_hub.integrations.shopify.adapter.ShopifyAdapter"
    
    def get_field(self, name: str) -> IntegrationField | None:
        """Get a field definition by name."""
        for f in self.fields:
            if f.name == name:
                return f
        return None
    
    def get_required_fields(self) -> list[str]:
        """Get list of required field names."""
        return [f.name for f in self.fields if f.required]
    
    def get_sensitive_fields(self) -> list[str]:
        """Get list of sensitive field names (should be masked in responses)."""
        return [f.name for f in self.fields if f.sensitive]
    
    def get_legacy_field_mapping(self) -> dict[str, str]:
        """Get mapping of new field names to legacy TenantConfiguration fields."""
        return {
            f.name: f.legacy_field
            for f in self.fields
            if f.legacy_field
        }


INTEGRATION_REGISTRY: dict[str, IntegrationDefinition] = {
    "openai": IntegrationDefinition(
        slug="openai",
        name="OpenAI",
        description="AI-powered assistance and automation using GPT models",
        category="ai",
        icon="brain",
        enabled_field_legacy="openai_integration_enabled",
        supports_multi_instance=True,
        fields=[
            IntegrationField(
                name="api_key",
                required=True,
                sensitive=True,
                description="OpenAI API key",
                legacy_field="openai_api_key"
            ),
            IntegrationField(
                name="default_model",
                default="gpt-4o-mini",
                description="Default model for completions",
                legacy_field="openai_default_model"
            ),
            IntegrationField(
                name="embedding_model",
                default="text-embedding-3-small",
                description="Model for text embeddings",
                legacy_field="openai_embedding_model"
            ),
            IntegrationField(
                name="max_retries",
                field_type="integer",
                default=5,
                description="Maximum retry attempts",
                legacy_field="openai_max_retries"
            ),
        ]
    ),
    
    "whatsapp": IntegrationDefinition(
        slug="whatsapp",
        name="WhatsApp Business",
        description="Customer messaging via WhatsApp Business API",
        category="messaging",
        icon="message-circle",
        enabled_field_legacy="whatsapp_integration_enabled",
        supports_multi_instance=True,
        auth_scope="tenant",
        supports_webhook=True,
        supports_oauth=True,
        supports_polling=False,
        webhook_path_suffix="whatsapp",
        adapter_module="central_hub.integrations.whatsapp.adapter.WhatsAppAdapter",
        fields=[
            IntegrationField(
                name="token",
                required=True,
                sensitive=True,
                description="WhatsApp API access token",
                legacy_field="whatsapp_token"
            ),
            IntegrationField(
                name="phone_id",
                required=True,
                description="WhatsApp phone number ID",
                legacy_field="whatsapp_phone_id"
            ),
            IntegrationField(
                name="business_account_id",
                required=True,
                description="WhatsApp Business Account ID",
                legacy_field="whatsapp_business_account_id"
            ),
            IntegrationField(
                name="url",
                default="https://graph.facebook.com/v18.0",
                description="WhatsApp API base URL",
                legacy_field="whatsapp_url"
            ),
            IntegrationField(
                name="name",
                description="Display name for this WhatsApp number",
                legacy_field="whatsapp_name"
            ),
            IntegrationField(
                name="catalog_id",
                description="Product catalog ID",
                legacy_field="whatsapp_catalog_id"
            ),
        ]
    ),
    
    "smtp": IntegrationDefinition(
        slug="smtp",
        name="Email (SMTP)",
        description="Email sending via SMTP",
        category="messaging",
        icon="mail",
        enabled_field_legacy="smtp_integration_enabled",
        supports_multi_instance=True,
        fields=[
            IntegrationField(
                name="host",
                required=True,
                description="SMTP server hostname",
                legacy_field="smtp_host"
            ),
            IntegrationField(
                name="port",
                field_type="integer",
                default=465,
                description="SMTP server port",
                legacy_field="smtp_port"
            ),
            IntegrationField(
                name="user",
                required=True,
                description="SMTP username",
                legacy_field="smtp_user"
            ),
            IntegrationField(
                name="password",
                required=True,
                sensitive=True,
                description="SMTP password",
                legacy_field="smtp_password"
            ),
            IntegrationField(
                name="use_tls",
                field_type="boolean",
                default=True,
                description="Use TLS encryption",
                legacy_field="smtp_use_tls"
            ),
            IntegrationField(
                name="from_address",
                description="Default sender address",
                legacy_field="smtp_from"
            ),
        ]
    ),
    
    "mercadopago": IntegrationDefinition(
        slug="mercadopago",
        name="Mercado Pago",
        description="Payment processing via Mercado Pago",
        category="payments",
        icon="credit-card",
        enabled_field_legacy="mercadopago_integration_enabled",
        supports_multi_instance=False,
        fields=[
            IntegrationField(
                name="public_key",
                required=True,
                description="Mercado Pago public key",
                legacy_field="mercadopago_public_key"
            ),
            IntegrationField(
                name="access_token",
                required=True,
                sensitive=True,
                description="Mercado Pago access token",
                legacy_field="mercadopago_access_token"
            ),
            IntegrationField(
                name="client_id",
                description="Mercado Pago client ID",
                legacy_field="mercadopago_client_id"
            ),
            IntegrationField(
                name="client_secret",
                sensitive=True,
                description="Mercado Pago client secret",
                legacy_field="mercadopago_client_secret"
            ),
            IntegrationField(
                name="webhook_secret",
                sensitive=True,
                description="Webhook signature secret",
                legacy_field="mercadopago_webhook_secret"
            ),
        ]
    ),
    
    "google": IntegrationDefinition(
        slug="google",
        name="Google APIs",
        description="Google services integration (Maps, etc.)",
        category="services",
        icon="map",
        enabled_field_legacy="google_integration_enabled",
        supports_multi_instance=False,
        fields=[
            IntegrationField(
                name="api_key",
                required=True,
                sensitive=True,
                description="Google API key (server-side, IP-restricted)",
                legacy_field="google_api_key"
            ),
            IntegrationField(
                name="browser_key",
                sensitive=False,
                description="Google Maps JavaScript API key (client-side, HTTP referrer-restricted)",
            ),
        ]
    ),
    
    "dac": IntegrationDefinition(
        slug="dac",
        name="DAC Courier",
        description="DAC courier integration for shipping",
        category="logistics",
        icon="truck",
        enabled_field_legacy="dac_integration_enabled",
        supports_multi_instance=False,
        fields=[
            IntegrationField(
                name="user",
                required=True,
                description="DAC username",
                legacy_field="dac_user"
            ),
            IntegrationField(
                name="password",
                required=True,
                sensitive=True,
                description="DAC password",
                legacy_field="dac_password"
            ),
            IntegrationField(
                name="rut",
                description="Company RUT",
                legacy_field="dac_rut"
            ),
            IntegrationField(
                name="sender_name",
                description="Sender name for shipments",
                legacy_field="dac_sender_name"
            ),
            IntegrationField(
                name="sender_phone",
                description="Sender phone number",
                legacy_field="dac_sender_phone"
            ),
            IntegrationField(
                name="base_url",
                description="DAC API base URL",
                legacy_field="dac_base_url"
            ),
            IntegrationField(
                name="notification_list",
                description="Comma-separated notification emails",
                legacy_field="dac_notification_list"
            ),
            IntegrationField(
                name="tracking_period",
                field_type="integer",
                default=30,
                description="Tracking period in days",
                legacy_field="dac_tracking_period"
            ),
            IntegrationField(
                name="polling_interval",
                field_type="integer",
                default=30,
                description="Polling interval in minutes",
                legacy_field="dac_polling_interval"
            ),
        ]
    ),
    
    "hiringroom": IntegrationDefinition(
        slug="hiringroom",
        name="HiringRoom",
        description="Recruitment platform integration",
        category="recruitment",
        icon="users",
        enabled_field_legacy="hiringroom_integration_enabled",
        supports_multi_instance=False,
        fields=[
            IntegrationField(
                name="client_id",
                required=True,
                description="HiringRoom client ID",
                legacy_field="hiringroom_client_id"
            ),
            IntegrationField(
                name="client_secret",
                required=True,
                sensitive=True,
                description="HiringRoom client secret",
                legacy_field="hiringroom_client_secret"
            ),
            IntegrationField(
                name="username",
                description="HiringRoom username",
                legacy_field="hiringroom_username"
            ),
            IntegrationField(
                name="password",
                sensitive=True,
                description="HiringRoom password",
                legacy_field="hiringroom_password"
            ),
        ]
    ),
    
    "psigma": IntegrationDefinition(
        slug="psigma",
        name="Psigma",
        description="Psychometric assessment platform",
        category="recruitment",
        icon="clipboard-check",
        enabled_field_legacy="psigma_integration_enabled",
        supports_multi_instance=False,
        fields=[
            IntegrationField(
                name="user",
                required=True,
                description="Psigma username",
                legacy_field="psigma_user"
            ),
            IntegrationField(
                name="password",
                required=True,
                sensitive=True,
                description="Psigma password",
                legacy_field="psigma_password"
            ),
            IntegrationField(
                name="token",
                sensitive=True,
                description="Psigma API token",
                legacy_field="psigma_token"
            ),
            IntegrationField(
                name="url",
                description="Psigma API URL",
                legacy_field="psigma_url"
            ),
        ]
    ),
    
    "zetasoftware": IntegrationDefinition(
        slug="zetasoftware",
        name="Zeta Software",
        description="Zeta Software ERP integration",
        category="erp",
        icon="database",
        enabled_field_legacy="zetaSoftware_integration_enabled",
        supports_multi_instance=False,
        fields=[
            IntegrationField(
                name="dev_code",
                required=True,
                description="Developer code",
                legacy_field="zetaSoftware_dev_code"
            ),
            IntegrationField(
                name="dev_key",
                required=True,
                sensitive=True,
                description="Developer key",
                legacy_field="zetaSoftware_dev_key"
            ),
            IntegrationField(
                name="company_code",
                required=True,
                description="Company code",
                legacy_field="zetaSoftware_company_code"
            ),
            IntegrationField(
                name="company_key",
                required=True,
                sensitive=True,
                description="Company key",
                legacy_field="zetaSoftware_company_key"
            ),
        ]
    ),
    
    "woocommerce": IntegrationDefinition(
        slug="woocommerce",
        name="WooCommerce",
        description="WooCommerce e-commerce integration",
        category="ecommerce",
        icon="shopping-cart",
        enabled_field_legacy="woocommerce_integration_enabled",
        supports_multi_instance=True,
        fields=[
            IntegrationField(
                name="site_url",
                required=True,
                description="WooCommerce store URL",
                legacy_field="woocommerce_site_url"
            ),
            IntegrationField(
                name="consumer_key",
                required=True,
                description="WooCommerce consumer key",
                legacy_field="woocommerce_consumer_key"
            ),
            IntegrationField(
                name="consumer_secret",
                required=True,
                sensitive=True,
                description="WooCommerce consumer secret",
                legacy_field="woocommerce_consumer_secret"
            ),
        ]
    ),
    
    "wordpress": IntegrationDefinition(
        slug="wordpress",
        name="WordPress",
        description="WordPress site integration",
        category="cms",
        icon="edit-3",
        enabled_field_legacy="wordpress_integration_enabled",
        supports_multi_instance=True,
        fields=[
            IntegrationField(
                name="site_url",
                required=True,
                description="WordPress site URL",
                legacy_field="wordpress_site_url"
            ),
            IntegrationField(
                name="username",
                required=True,
                description="WordPress username",
                legacy_field="wordpress_username"
            ),
            IntegrationField(
                name="app_password",
                required=True,
                sensitive=True,
                description="WordPress application password",
                legacy_field="wordpress_app_password"
            ),
        ]
    ),
    
    "assistants": IntegrationDefinition(
        slug="assistants",
        name="AI Assistants",
        description="AI assistant and chatbot configuration",
        category="ai",
        icon="bot",
        enabled_field_legacy="assistants_enabled",
        supports_multi_instance=False,
        fields=[
            IntegrationField(
                name="default_id",
                description="Default assistant ID",
                legacy_field="assistants_default_id"
            ),
            IntegrationField(
                name="conversation_handler",
                default="assistant",
                description="Conversation handler type",
                legacy_field="conversation_handler"
            ),
            IntegrationField(
                name="smart_reply_enabled",
                field_type="boolean",
                default=False,
                description="Enable smart reply suggestions",
                legacy_field="assistant_smart_reply_enabled"
            ),
            IntegrationField(
                name="output_formatting_instructions",
                description="Custom output formatting instructions",
                legacy_field="assistant_output_formatting_instructions"
            ),
            IntegrationField(
                name="output_schema",
                description="JSON schema for structured output",
                legacy_field="assistant_output_schema"
            ),
            IntegrationField(
                name="inactivity_limit",
                field_type="integer",
                default=30,
                description="Inactivity timeout in minutes",
                legacy_field="assistants_inactivity_limit"
            ),
            IntegrationField(
                name="chatbot_enabled",
                field_type="boolean",
                default=False,
                description="Enable chatbot mode",
                legacy_field="chatbot_enabled"
            ),
            IntegrationField(
                name="default_agent_id",
                description="Default agent ID for conversations",
                legacy_field="default_agent_id"
            ),
        ]
    ),
    
    "shopify": IntegrationDefinition(
        slug="shopify",
        name="Shopify",
        description="Shopify e-commerce integration - Receive data from Shopify as source of truth",
        category="ecommerce",
        icon="shopping-bag",
        supports_multi_instance=True,
        auth_scope="tenant",
        supports_webhook=True,
        supports_oauth=True,
        supports_polling=False,
        webhook_path_suffix="shopify",
        adapter_module="central_hub.integrations.shopify.adapter.ShopifyAdapter",
        fields=[
            IntegrationField(
                name="direction",
                field_type="choice",
                choices=[
                    ("receive", "Receive from Shopify (Shopify as source of truth)"),
                    ("send", "Send to Shopify (CRM as source of truth)"),
                ],
                default="receive",
                description="Data flow direction"
            ),
            IntegrationField(
                name="store_url",
                required=True,
                description="Shopify store URL (e.g., mystore.myshopify.com)"
            ),
            IntegrationField(
                name="access_token",
                required=True,
                sensitive=True,
                description="Shopify Admin API access token"
            ),
            IntegrationField(
                name="api_version",
                default="2024-01",
                description="Shopify API version"
            ),
            IntegrationField(
                name="webhook_secret",
                sensitive=True,
                description="Webhook signature verification secret for validating incoming webhooks"
            ),
            IntegrationField(
                name="receive_products",
                field_type="boolean",
                default=True,
                description="Receive/sync product data from Shopify into CRM"
            ),
            IntegrationField(
                name="receive_customers",
                field_type="boolean",
                default=True,
                description="Receive/sync customer data from Shopify into CRM"
            ),
            IntegrationField(
                name="receive_orders",
                field_type="boolean",
                default=True,
                description="Receive/sync order data from Shopify into CRM"
            ),
            IntegrationField(
                name="receive_inventory",
                field_type="boolean",
                default=True,
                description="Receive/sync inventory data from Shopify into CRM"
            ),
            IntegrationField(
                name="send_inventory_updates",
                field_type="boolean",
                default=False,
                description="Send inventory updates from CRM back to Shopify"
            ),
            IntegrationField(
                name="send_order_updates",
                field_type="boolean",
                default=False,
                description="Send order status updates from CRM back to Shopify"
            ),
        ]
    ),
    
    "bitsistemas": IntegrationDefinition(
        slug="bitsistemas",
        name="Bit-Sistemas ERP",
        description="ERP integration for accounting, inventory, and business management",
        category="erp",
        icon="database",
        supports_multi_instance=False,
        fields=[
            IntegrationField(
                name="base_url",
                required=True,
                description="Bit-Sistemas API base URL"
            ),
            IntegrationField(
                name="api_key",
                required=True,
                sensitive=True,
                description="API authentication key"
            ),
            IntegrationField(
                name="api_secret",
                sensitive=True,
                description="API secret for signature verification"
            ),
            IntegrationField(
                name="company_code",
                required=True,
                description="Company/tenant identifier in Bit-Sistemas"
            ),
            IntegrationField(
                name="branch_code",
                description="Branch/location code (if applicable)"
            ),
            IntegrationField(
                name="sync_customers",
                field_type="boolean",
                default=True,
                description="Sync customers with CRM contacts"
            ),
            IntegrationField(
                name="sync_invoices",
                field_type="boolean",
                default=True,
                description="Sync invoices and billing"
            ),
            IntegrationField(
                name="sync_products",
                field_type="boolean",
                default=True,
                description="Sync product catalog"
            ),
            IntegrationField(
                name="sync_inventory",
                field_type="boolean",
                default=True,
                description="Sync inventory levels"
            ),
            IntegrationField(
                name="webhook_url",
                description="Webhook callback URL for real-time updates"
            ),
        ]
    ),
}


def get_integration(slug: str) -> IntegrationDefinition | None:
    """Get integration definition by slug."""
    return INTEGRATION_REGISTRY.get(slug)


def get_integration_schema(slug: str) -> dict[str, Any] | None:
    """Get JSON-schema-like definition for an integration."""
    definition = INTEGRATION_REGISTRY.get(slug)
    if not definition:
        return None
    
    properties = {}
    required = []
    
    for f in definition.fields:
        prop: dict[str, Any] = {"description": f.description}
        
        if f.field_type == "string":
            prop["type"] = "string"
        elif f.field_type == "integer":
            prop["type"] = "integer"
        elif f.field_type == "boolean":
            prop["type"] = "boolean"
        else:
            prop["type"] = "string"
        
        if f.default is not None:
            prop["default"] = f.default
        
        properties[f.name] = prop
        
        if f.required:
            required.append(f.name)
    
    return {
        "type": "object",
        "properties": properties,
        "required": required,
    }


def get_integration_fields(slug: str) -> list[str]:
    """Get list of field names for an integration."""
    definition = INTEGRATION_REGISTRY.get(slug)
    if not definition:
        return []
    return [f.name for f in definition.fields]


def get_required_fields(slug: str) -> list[str]:
    """Get list of required field names for an integration."""
    definition = INTEGRATION_REGISTRY.get(slug)
    if not definition:
        return []
    return definition.get_required_fields()


def get_sensitive_fields(slug: str) -> list[str]:
    """Get list of sensitive field names (should be masked)."""
    definition = INTEGRATION_REGISTRY.get(slug)
    if not definition:
        return []
    return definition.get_sensitive_fields()


def validate_integration_config(
    slug: str, 
    config: dict[str, Any],
    apply_defaults: bool = True,
) -> list[str]:
    """
    Validate config dict against integration schema.
    Returns list of error messages (empty if valid).
    
    Args:
        slug: Integration type slug
        config: Configuration dictionary to validate
        apply_defaults: If True, consider default values when checking required fields
    """
    definition = INTEGRATION_REGISTRY.get(slug)
    if not definition:
        return [f"Unknown integration: {slug}"]
    
    errors = []
    
    for f in definition.fields:
        value = config.get(f.name)
        
        if f.required:
            has_value = value is not None and value != ""
            has_default = apply_defaults and f.default is not None
            if not has_value and not has_default:
                errors.append(f"Missing required field: {f.name}")
                continue
        
        if value is not None:
            if f.field_type == "integer" and not isinstance(value, int):
                try:
                    int(value)
                except (ValueError, TypeError):
                    errors.append(f"Field {f.name} must be an integer")
            
            elif f.field_type == "boolean" and not isinstance(value, bool):
                if value not in ("true", "false", True, False, 0, 1):
                    errors.append(f"Field {f.name} must be a boolean")
    
    return errors


def apply_config_defaults(slug: str, config: dict[str, Any]) -> dict[str, Any]:
    """
    Apply default values from schema to config dict.
    Returns new config dict with defaults merged in.
    """
    definition = INTEGRATION_REGISTRY.get(slug)
    if not definition:
        return config
    
    result = {}
    for f in definition.fields:
        if f.name in config:
            result[f.name] = config[f.name]
        elif f.default is not None:
            result[f.name] = f.default
    
    return result


def get_legacy_to_new_mapping(slug: str) -> dict[str, str]:
    """
    Get mapping from legacy TenantConfiguration field names to new config keys.
    Returns: {legacy_field_name: new_config_key}
    """
    definition = INTEGRATION_REGISTRY.get(slug)
    if not definition:
        return {}
    
    return {
        f.legacy_field: f.name
        for f in definition.fields
        if f.legacy_field
    }


def get_new_to_legacy_mapping(slug: str) -> dict[str, str]:
    """
    Get mapping from new config keys to legacy TenantConfiguration field names.
    Returns: {new_config_key: legacy_field_name}
    """
    definition = INTEGRATION_REGISTRY.get(slug)
    if not definition:
        return {}
    
    return {
        f.name: f.legacy_field
        for f in definition.fields
        if f.legacy_field
    }


def list_integrations(category: str | None = None) -> list[IntegrationDefinition]:
    """List all integration definitions, optionally filtered by category."""
    integrations = list(INTEGRATION_REGISTRY.values())
    if category:
        integrations = [i for i in integrations if i.category == category]
    return integrations


def list_categories() -> list[str]:
    """Get list of unique integration categories."""
    return list(set(i.category for i in INTEGRATION_REGISTRY.values()))
