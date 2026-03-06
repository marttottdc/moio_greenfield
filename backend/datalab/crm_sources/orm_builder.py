"""
ORM Builder for CRM Views.

Converts query_spec_json to Django QuerySet.
"""
from __future__ import annotations

import logging
from typing import Any

import pandas as pd
from django.db.models import Sum, Count, Avg, Max, Min, F
from django.db.models.functions import TruncDate

from crm.models import Deal, Contact  # noqa
from datalab.crm_sources.models import CRMView

logger = logging.getLogger(__name__)


class CRMQueryORMBuilderError(Exception):
    """Raised when ORM building fails."""
    pass


class CRMQueryORMBuilder:
    """Converts query_spec_json to Django QuerySet."""
    
    AGGREGATION_FUNCTIONS = {
        'sum': Sum,
        'count': Count,
        'avg': Avg,
        'average': Avg,
        'max': Max,
        'min': Min,
    }
    
    def build_queryset(
        self,
        view: CRMView,
        filters: dict[str, Any] | None = None
    ) -> pd.DataFrame:
        """
        Build QuerySet from CRMView and convert to DataFrame.
        
        Args:
            view: CRMView instance
            filters: User-provided filters
            
        Returns:
            DataFrame with query results
        """
        query_spec = view.query_spec_json
        base_entity = query_spec.get('base_entity')
        
        if base_entity == 'deal':
            qs = Deal.objects.filter(tenant=view.tenant)
        elif base_entity == 'contact':
            qs = Contact.objects.filter(tenant=view.tenant)
        else:
            raise CRMQueryORMBuilderError(f"Unknown base_entity: {base_entity}")
        
        # Apply default filters
        for key, value in view.default_filters_json.items():
            qs = self._apply_filter(qs, base_entity, key, value)
        
        # Apply user filters
        if filters:
            for key, value in filters.items():
                if key not in view.allowed_filters_json:
                    logger.warning(f"Filter '{key}' not in allowed_filters, skipping")
                    continue
                qs = self._apply_filter(qs, base_entity, key, value)
        
        # Apply joins
        joins = query_spec.get('joins', [])
        for join in joins:
            qs = self._apply_join(qs, base_entity, join)
        
        # Apply aggregations and group by
        aggregations = query_spec.get('aggregations', [])
        grain = query_spec.get('grain')
        
        if aggregations or grain:
            qs = self._apply_aggregations(qs, base_entity, aggregations, grain, query_spec)
        else:
            # Simple projections without aggregation
            projections = query_spec.get('projections', [])
            if projections:
                qs = self._apply_projections(qs, projections)
        
        # Convert to DataFrame
        values_list = []
        if aggregations or grain:
            # Aggregated query
            for row in qs:
                row_dict = {}
                for projection in query_spec.get('projections', []):
                    alias = projection.get('alias') or projection['field'].split('.')[-1]
                    row_dict[alias] = getattr(row, alias, None)
                
                # Add aggregation values
                for agg in aggregations:
                    alias = agg.get('alias')
                    if alias:
                        row_dict[alias] = getattr(row, alias, None)
                
                values_list.append(row_dict)
        else:
            # Regular query
            projections = query_spec.get('projections', [])
            if projections:
                # Use values() with projection fields
                field_names = []
                for proj in projections:
                    field_name = self._get_field_name(base_entity, proj['field'])
                    alias = proj.get('alias')
                    if alias:
                        field_names.append(f"{field_name}__{alias}")
                    else:
                        field_names.append(field_name)
                
                # Simplified: get all fields and map
                for obj in qs[:10000]:  # Limit for safety
                    row_dict = {}
                    for proj in projections:
                        field_path = proj['field']
                        alias = proj.get('alias') or field_path.split('.')[-1]
                        value = self._get_field_value(obj, field_path, base_entity)
                        row_dict[alias] = value
                    values_list.append(row_dict)
            else:
                # No projections: use all fields
                for obj in qs[:10000]:
                    row_dict = {}
                    for field in obj._meta.fields:
                        row_dict[field.name] = getattr(obj, field.name, None)
                    values_list.append(row_dict)
        
        if not values_list:
            # Return empty DataFrame with correct schema
            columns = [col['name'] for col in view.schema_json]
            return pd.DataFrame(columns=columns)
        
        df = pd.DataFrame(values_list)
        return df
    
    def _apply_filter(self, qs: Any, base_entity: str, key: str, value: Any) -> Any:
        """Apply a filter to the QuerySet."""
        # Map filter keys to field paths
        field_map = {
            'status': f'{base_entity}__status',
            'owner_id': f'{base_entity}__owner_id',
            'stage_id': f'{base_entity}__stage_id',
            'contact_id': f'{base_entity}__contact_id',
            'created_at': f'{base_entity}__created_at',
            'date_from': f'{base_entity}__created_at__gte',
            'date_to': f'{base_entity}__created_at__lte',
            'expected_close_date': f'{base_entity}__expected_close_date',
        }
        
        filter_key = field_map.get(key, f'{base_entity}__{key}')
        return qs.filter(**{filter_key: value})
    
    def _apply_join(self, qs: Any, base_entity: str, join: dict[str, Any]) -> Any:
        """Apply a join to the QuerySet."""
        join_model = join.get('model')
        
        if base_entity == 'deal' and join_model == 'contact':
            qs = qs.select_related('contact')
        elif base_entity == 'contact' and join_model == 'deal':
            # Prefetch deals for contacts
            qs = qs.prefetch_related('deals')
        
        return qs
    
    def _apply_aggregations(
        self,
        qs: Any,
        base_entity: str,
        aggregations: list[dict[str, Any]],
        grain: str | None,
        query_spec: dict[str, Any]
    ) -> Any:
        """Apply aggregations and group by."""
        annotate_kwargs = {}
        
        # Build aggregation annotations
        for agg in aggregations:
            field = agg['field']
            func_name = agg['function'].lower()
            alias = agg['alias']
            
            # Resolve field path
            field_path = self._get_aggregation_field_path(base_entity, field)
            
            # Get aggregation function
            agg_func = self.AGGREGATION_FUNCTIONS.get(func_name)
            if not agg_func:
                raise CRMQueryORMBuilderError(f"Unknown aggregation function: {func_name}")
            
            annotate_kwargs[alias] = agg_func(field_path)
        
        # Apply group by
        if grain == 'day':
            # Group by day (date truncation)
            qs = qs.annotate(day=TruncDate('created_at'))
            qs = qs.values('day')
        elif grain == 'contact':
            # Group by contact
            if base_entity == 'deal':
                qs = qs.values('contact_id', 'contact__fullname')
            else:
                qs = qs.values('user_id', 'fullname')
        elif grain == 'deal':
            # Group by deal (no aggregation, just per-deal)
            pass
        else:
            # Default: group by base entity primary key
            if base_entity == 'deal':
                qs = qs.values('id')
            elif base_entity == 'contact':
                qs = qs.values('user_id')
        
        # Apply annotations
        if annotate_kwargs:
            qs = qs.annotate(**annotate_kwargs)
        
        return qs
    
    def _apply_projections(self, qs: Any, projections: list[dict[str, Any]]) -> Any:
        """Apply projections (field selection)."""
        # For now, return qs as-is
        # Projections are handled when converting to DataFrame
        return qs
    
    def _get_field_name(self, base_entity: str, field_path: str) -> str:
        """Convert field path to Django field name."""
        # Simple implementation: remove model prefix
        if '.' in field_path:
            parts = field_path.split('.')
            if len(parts) == 2:
                return parts[1]
            elif len(parts) == 3:
                # e.g., "deal.contact.fullname"
                return f"{parts[1]}__{parts[2]}"
        return field_path
    
    def _get_field_value(self, obj: Any, field_path: str, base_entity: str) -> Any:
        """Get field value from object using path."""
        parts = field_path.split('.')
        value = obj
        
        for part in parts[1:]:  # Skip base entity
            if value is None:
                return None
            if hasattr(value, part):
                value = getattr(value, part)
            else:
                return None
        
        return value
    
    def _get_aggregation_field_path(self, base_entity: str, field: str) -> str:
        """Get field path for aggregation."""
        if '.' in field:
            parts = field.split('.')
            if len(parts) == 2:
                return parts[1]
            elif len(parts) == 3:
                return f"{parts[1]}__{parts[2]}"
        return field
