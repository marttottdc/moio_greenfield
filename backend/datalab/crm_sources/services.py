"""
CRM Query Engine for Data Lab.

Executes queries on CRM Views and returns ResultSets.
"""
from __future__ import annotations

import logging
from typing import Any

from django.db.models import Q

from datalab.core.models import ResultSet, ResultSetOrigin, ResultSetStorage
from datalab.core.serialization import serialize_for_json
from datalab.core.storage import get_storage
from datalab.crm_sources.models import CRMView
from datalab.crm_sources.orm_builder import CRMQueryORMBuilder, CRMQueryORMBuilderError

logger = logging.getLogger(__name__)


class CRMQueryEngineError(Exception):
    """Raised when CRM query execution fails."""
    pass


class CRMQueryEngine:
    """
    Executes queries on CRMViews using Django ORM.
    
    Always applies tenant scoping.
    """
    
    THRESHOLD_ROWS = 10000
    PREVIEW_LIMIT = 200
    
    def __init__(self):
        self.orm_builder = CRMQueryORMBuilder()
        self.storage = get_storage()
    
    def execute(
        self,
        view_key: str,
        tenant: Any,
        filters: dict[str, Any] | None = None,
        projection: list[str] | None = None,
        limit: int | None = None,
        materialize: bool = False,
        user: Any = None
    ) -> ResultSet:
        """
        Execute query on CRMView.
        
        Args:
            view_key: Key of the CRMView (e.g., 'crm.deals.active')
            tenant: Tenant instance
            filters: Optional filters to apply
            projection: Optional list of columns to return (not yet implemented)
            limit: Optional row limit
            materialize: Force materialization as Parquet
            user: User executing the query
            
        Returns:
            ResultSet with query results
            
        Raises:
            CRMQueryEngineError: If execution fails
        """
        # Load CRMView
        try:
            view = CRMView.objects.get(
                (Q(tenant=tenant) | Q(is_global=True)),
                key=view_key,
                is_active=True
            )
        except CRMView.DoesNotExist:
            raise CRMQueryEngineError(f"CRMView '{view_key}' not found for tenant")
        
        # Validate filters against allowed_filters
        if filters:
            invalid_filters = [
                key for key in filters.keys()
                if key not in view.allowed_filters_json
            ]
            if invalid_filters:
                raise CRMQueryEngineError(
                    f"Invalid filters: {invalid_filters}. "
                    f"Allowed: {view.allowed_filters_json}"
                )
        
        try:
            # Build and execute QuerySet
            df = self.orm_builder.build_queryset(view, filters)
            
            # Apply limit if specified
            if limit:
                df = df.head(limit)
            
            # Create ResultSet
            resultset = self._create_resultset(
                df,
                view,
                filters,
                tenant,
                user
            )
            
            # Materialize if needed
            if materialize or len(df) > self.THRESHOLD_ROWS:
                self._materialize_resultset(resultset, df)
            
            # Generate preview - convert Timestamps to ISO strings for JSON serialization
            preview_dict = df.head(self.PREVIEW_LIMIT).to_dict(orient='records')
            resultset.preview_json = serialize_for_json(preview_dict)
            resultset.save()
            
            return resultset
            
        except CRMQueryORMBuilderError as e:
            raise CRMQueryEngineError(f"Query building failed: {e}") from e
        except Exception as e:
            logger.error(f"CRM query execution failed: {e}", exc_info=True)
            raise CRMQueryEngineError(f"Query execution failed: {e}") from e
    
    def _create_resultset(
        self,
        df: Any,
        view: CRMView,
        filters: dict[str, Any] | None,
        tenant: Any,
        user: Any
    ) -> ResultSet:
        """Create ResultSet from DataFrame."""
        # Use view's schema
        schema = view.schema_json
        
        # Build lineage (minimum required)
        lineage = {
            "origin": ResultSetOrigin.CRM_QUERY,
            "source": {"type": "crm_view", "key": view.key},
            "filters": filters or {},
        }
        
        # Create ResultSet
        resultset = ResultSet.objects.create(
            tenant=tenant,
            origin=ResultSetOrigin.CRM_QUERY,
            schema_json=schema,
            row_count=len(df),
            storage=ResultSetStorage.MEMORY,
            lineage_json=lineage,
            created_by=user
        )
        
        return resultset
    
    def _materialize_resultset(self, resultset: ResultSet, df: Any) -> None:
        """Materialize ResultSet as Parquet in S3."""
        try:
            storage_key = self.storage.save_parquet(df, resultset.id)
            resultset.storage = ResultSetStorage.PARQUET.value
            resultset.storage_key = storage_key
            resultset.save(update_fields=['storage', 'storage_key'])
            logger.info(f"Materialized CRM query ResultSet {resultset.id} as Parquet")
        except Exception as e:
            logger.error(f"Failed to materialize ResultSet {resultset.id}: {e}")
            # Don't fail the query, just log the error
