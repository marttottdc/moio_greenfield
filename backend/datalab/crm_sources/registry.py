"""
Registry for predefined CRM Views.

Defines standard semantic views that can be initialized for tenants.
"""
from __future__ import annotations

from typing import Any

from datalab.crm_sources.models import CRMView
from portal.models import Tenant


class CRMViewRegistry:
    """Registry for CRM View definitions."""
    
    DEFAULT_VIEWS: dict[str, dict[str, Any]] = {
        "crm.deals.active": {
            "label": "Active Deals",
            "description": "All active (open) deals",
            "schema": [
                {"name": "id", "type": "uuid", "nullable": False},
                {"name": "title", "type": "string", "nullable": False},
                {"name": "value", "type": "decimal", "nullable": True},
                {"name": "currency", "type": "string", "nullable": True},
                {"name": "status", "type": "string", "nullable": False},
                {"name": "stage", "type": "string", "nullable": True},
                {"name": "contact_id", "type": "string", "nullable": True},
                {"name": "contact_name", "type": "string", "nullable": True},
                {"name": "owner_id", "type": "uuid", "nullable": True},
                {"name": "created_at", "type": "date", "nullable": False},
            ],
            "query_spec": {
                "base_entity": "deal",
                "joins": [
                    {
                        "type": "left",
                        "model": "contact",
                        "on": "deal.contact_id = contact.user_id",
                        "fields": ["contact.user_id as contact_id", "contact.fullname as contact_name"]
                    }
                ],
                "projections": [
                    {"field": "deal.id", "alias": "id"},
                    {"field": "deal.title", "alias": "title"},
                    {"field": "deal.value", "alias": "value"},
                    {"field": "deal.currency", "alias": "currency"},
                    {"field": "deal.status", "alias": "status"},
                    {"field": "deal.stage.name", "alias": "stage"},
                    {"field": "deal.contact_id", "alias": "contact_id"},
                    {"field": "contact.fullname", "alias": "contact_name"},
                    {"field": "deal.owner_id", "alias": "owner_id"},
                    {"field": "deal.created_at", "alias": "created_at"},
                ],
                "grain": "deal",
            },
            "allowed_filters": ["status", "owner_id", "stage_id", "created_at", "expected_close_date"],
            "default_filters": {"status": "open"},
        },
        
        "crm.sales.by_day": {
            "label": "Sales by Day",
            "description": "Daily aggregated sales from won deals",
            "schema": [
                {"name": "day", "type": "date", "nullable": False},
                {"name": "total_amount", "type": "decimal", "nullable": True},
                {"name": "deal_count", "type": "integer", "nullable": False},
                {"name": "avg_deal_value", "type": "decimal", "nullable": True},
            ],
            "query_spec": {
                "base_entity": "deal",
                "aggregations": [
                    {"field": "value", "function": "sum", "alias": "total_amount"},
                    {"field": "id", "function": "count", "alias": "deal_count"},
                    {"field": "value", "function": "avg", "alias": "avg_deal_value"},
                ],
                "grain": "day",
                "group_by": "DATE(actual_close_date)",
            },
            "allowed_filters": ["date_from", "date_to", "owner_id"],
            "default_filters": {"status": "won"},
        },
        
        "crm.contacts.with_deals": {
            "label": "Contacts with Deals",
            "description": "Contacts that have associated deals",
            "schema": [
                {"name": "contact_id", "type": "string", "nullable": False},
                {"name": "fullname", "type": "string", "nullable": True},
                {"name": "email", "type": "string", "nullable": True},
                {"name": "phone", "type": "string", "nullable": True},
                {"name": "deal_count", "type": "integer", "nullable": False},
                {"name": "total_deal_value", "type": "decimal", "nullable": True},
                {"name": "last_deal_date", "type": "date", "nullable": True},
            ],
            "query_spec": {
                "base_entity": "contact",
                "joins": [
                    {
                        "type": "left",
                        "model": "deal",
                        "on": "contact.user_id = deal.contact_id",
                    }
                ],
                "aggregations": [
                    {"field": "deal.id", "function": "count", "alias": "deal_count"},
                    {"field": "deal.value", "function": "sum", "alias": "total_deal_value"},
                    {"field": "deal.actual_close_date", "function": "max", "alias": "last_deal_date"},
                ],
                "projections": [
                    {"field": "contact.user_id", "alias": "contact_id"},
                    {"field": "contact.fullname", "alias": "fullname"},
                    {"field": "contact.email", "alias": "email"},
                    {"field": "contact.phone", "alias": "phone"},
                ],
                "grain": "contact",
                "having": "deal_count > 0",
            },
            "allowed_filters": ["status", "owner_id", "created_at"],
            "default_filters": {},
        },
    }
    
    @classmethod
    def initialize_defaults(cls, tenant: Tenant) -> list[CRMView]:
        """
        Initialize default CRM Views for a tenant.
        
        Args:
            tenant: Tenant to initialize views for
            
        Returns:
            List of created CRMView instances
        """
        created_views = []
        
        for key, definition in cls.DEFAULT_VIEWS.items():
            # Check if view already exists
            if CRMView.objects.filter(tenant=tenant, key=key).exists():
                continue
            
            view = CRMView.objects.create(
                tenant=tenant,
                key=key,
                label=definition["label"],
                description=definition.get("description", ""),
                schema_json=definition["schema"],
                query_spec_json=definition["query_spec"],
                allowed_filters_json=definition.get("allowed_filters", []),
                default_filters_json=definition.get("default_filters", {}),
                is_active=True,
                is_global=False
            )
            created_views.append(view)
        
        return created_views
    
    @classmethod
    def get_view_definition(cls, key: str) -> dict[str, Any] | None:
        """Get view definition by key."""
        return cls.DEFAULT_VIEWS.get(key)
