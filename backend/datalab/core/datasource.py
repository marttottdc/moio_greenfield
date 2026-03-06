"""
DataSourceRef resolver: resolves references to ResultSets from various sources.
"""
from __future__ import annotations

from typing import Any

from datalab.core.models import ResultSet
from datalab.crm_sources.models import CRMView
from datalab.crm_sources.services import CRMQueryEngine, CRMQueryEngineError


class DataSourceResolverError(Exception):
    """Raised when datasource resolution fails."""


def resolve_datasource(ref: dict, tenant) -> ResultSet:
    """
    Resolve a datasource reference to a ResultSet.

    Supported refs:
    - {"kind": "resultset", "id": "uuid"}
    - {"kind": "crm_view", "key": "crm.deals.active", "filters": {...}}
    """
    kind = ref.get("kind")
    if kind == "resultset":
        rs_id = ref.get("id")
        if not rs_id:
            raise DataSourceResolverError("resultset ref requires 'id'")
        try:
            return ResultSet.objects.get(id=rs_id, tenant=tenant)
        except ResultSet.DoesNotExist:
            raise DataSourceResolverError(f"ResultSet {rs_id} not found for tenant")

    if kind == "crm_view":
        view_key = ref.get("key")
        if not view_key:
            raise DataSourceResolverError("crm_view ref requires 'key'")
        filters = ref.get("filters", {})
        try:
            engine = CRMQueryEngine()
            return engine.execute(view_key=view_key, tenant=tenant, filters=filters)
        except (CRMQueryEngineError, CRMView.DoesNotExist) as e:
            raise DataSourceResolverError(str(e))

    raise DataSourceResolverError(f"Unknown datasource kind: {kind}")
