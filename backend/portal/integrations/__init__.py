"""
Portal Integrations Module

This module provides a flexible, extensible integration configuration system
that supports multi-instance configurations per tenant.

Usage:
    from portal.integrations.models import IntegrationConfig
    from portal.integrations.registry import INTEGRATION_REGISTRY, get_integration_schema
    
    # Get all WhatsApp configs for a tenant
    configs = IntegrationConfig.objects.filter(tenant=tenant, slug="whatsapp")
    
    # Get schema for validation
    schema = get_integration_schema("whatsapp")
    
API Endpoints:
    GET  /api/v1/integrations/                       - List available integrations
    GET  /api/v1/integrations/categories/            - List integration categories  
    GET  /api/v1/integrations/{slug}/schema/         - Get integration schema
    GET  /api/v1/integrations/{slug}/                - List configs for integration
    POST /api/v1/integrations/{slug}/                - Create new config
    GET  /api/v1/integrations/{slug}/{instance_id}/  - Get specific config
    PATCH /api/v1/integrations/{slug}/{instance_id}/ - Update config
    PUT  /api/v1/integrations/{slug}/{instance_id}/  - Replace config
    DELETE /api/v1/integrations/{slug}/{instance_id}/ - Delete config
"""

from portal.integrations.models import IntegrationConfig
from portal.integrations.registry import (
    INTEGRATION_REGISTRY,
    IntegrationDefinition,
    IntegrationField,
    get_integration,
    get_integration_schema,
    get_integration_fields,
    get_required_fields,
    get_sensitive_fields,
    validate_integration_config,
    list_integrations,
    list_categories,
)

__all__ = [
    "IntegrationConfig",
    "IntegrationDefinition",
    "IntegrationField",
    "INTEGRATION_REGISTRY",
    "get_integration",
    "get_integration_schema",
    "get_integration_fields",
    "get_required_fields",
    "get_sensitive_fields",
    "validate_integration_config",
    "list_integrations",
    "list_categories",
]
