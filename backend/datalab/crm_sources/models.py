"""
CRM View models for Data Lab.

Defines semantic views of CRM data as queryable data sources.
"""
from __future__ import annotations

import uuid

from django.db import models

from central_hub.models import Tenant, TenantScopedModel


class CRMView(TenantScopedModel):
    """
    Semantic view of CRM data exposed as a queryable table.
    
    Examples:
    - crm.sales.by_day.v1
    - crm.deals.active.v1
    - crm.contacts.with_deals.v1
    """
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name='datalab_crm_views')
    key = models.CharField(
        max_length=100,
        db_index=True,
        help_text="Unique identifier for this view (e.g., 'crm.sales.by_day.v1')"
    )
    label = models.CharField(max_length=200, help_text="Human-readable label")
    description = models.TextField(blank=True)
    
    # Schema definition
    schema_json = models.JSONField(
        help_text="Column definitions: [{'name': 'col', 'type': 'string', 'nullable': bool}]"
    )
    
    # Query specification: how to resolve this view
    query_spec_json = models.JSONField(
        help_text="Query specification: {'base_entity': 'deal', 'joins': [...], 'projections': [...], 'aggregations': [...]}"
    )
    
    # Filters allowed for this view
    allowed_filters_json = models.JSONField(
        default=list,
        blank=True,
        help_text="List of allowed filter keys: ['date_from', 'date_to', 'owner_id', ...]"
    )
    
    # Default filters to always apply
    default_filters_json = models.JSONField(
        default=dict,
        blank=True,
        help_text="Default filters: {'status': 'active', ...}"
    )
    
    is_active = models.BooleanField(default=True)
    is_global = models.BooleanField(
        default=False,
        help_text="If True, this view is available to all tenants (system-wide)"
    )
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'datalab_crm_view'
        verbose_name = 'CRM View'
        verbose_name_plural = 'CRM Views'
        unique_together = ('tenant', 'key')
        indexes = [
            models.Index(fields=['tenant', 'key']),
            models.Index(fields=['tenant', 'is_active']),
            models.Index(fields=['is_global', 'is_active']),
        ]
    
    def __str__(self) -> str:
        return f"{self.label} ({self.key})"
