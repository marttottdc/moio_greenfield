"""
Resolve DataLab parameter references in Flow Script input payloads.

Before a Flow Script run is created (from the flow_script node or from the API),
payloads can contain references like:

    {"$datalab_resultset": {"id": "<uuid>", "mode": "preview", "limit": 200}}

These are resolved (tenant-scoped, with row/byte limits) and replaced with
the actual schema + preview JSON so the script receives real data without
needing DB access in the sandbox.

Hook points:
- flows/core/registry.py: _exec_flow_script, after _render_deep(input_payload)
- flows/api_script_views.py: api_script_execute, after building params, before FlowScriptRun.objects.create
"""
from __future__ import annotations

import json
import logging
from typing import Any, Dict

logger = logging.getLogger(__name__)

# Limits for hydrated data to avoid huge payloads
MAX_PREVIEW_ROWS = 500
MAX_HYDRATED_BYTES = 2 * 1024 * 1024  # 2MB


def _resolve_one_resultset_ref(
    ref: Dict[str, Any],
    tenant_id: str,
) -> Dict[str, Any]:
    """
    Resolve a single {"$datalab_resultset": {"id": "...", "mode": "preview", "limit": N}}.
    Returns a dict with schema_json, row_count, preview_json (if mode is preview), etc.
    """
    from datalab.core.models import ResultSet

    rs_id = ref.get("id")
    if not rs_id:
        return {"error": "Missing id in $datalab_resultset"}
    mode = (ref.get("mode") or "preview").lower()
    limit = min(MAX_PREVIEW_ROWS, max(0, int(ref.get("limit") or 200)))

    try:
        resultset = ResultSet.objects.get(id=rs_id, tenant_id=tenant_id)
    except ResultSet.DoesNotExist:
        return {"error": f"ResultSet {rs_id} not found"}

    out = {
        "resultset_id": str(resultset.id),
        "schema_json": resultset.schema_json or {},
        "row_count": resultset.row_count,
        "is_json_object": getattr(resultset, "is_json_object", False),
        "origin": resultset.origin,
    }
    if mode == "preview" and resultset.preview_json:
        out["preview_json"] = list(resultset.preview_json)[:limit]
    else:
        out["preview_json"] = []
    return out


def _walk_and_resolve(value: Any, tenant_id: str, bytes_so_far: list) -> Any:
    """
    Recursively walk a payload and replace any value that is exactly
    a dict with key "$datalab_resultset" (and value the ref spec) with resolved data.
    bytes_so_far is a mutable list with one int to track total size and enforce MAX_HYDRATED_BYTES.
    """
    if bytes_so_far[0] > MAX_HYDRATED_BYTES:
        return value

    if isinstance(value, dict):
        if set(value.keys()) == {"$datalab_resultset"} and isinstance(value.get("$datalab_resultset"), dict):
            resolved = _resolve_one_resultset_ref(value["$datalab_resultset"], tenant_id)
            chunk = json.dumps(resolved, default=str)
            bytes_so_far[0] += len(chunk.encode("utf-8"))
            return resolved
        return {k: _walk_and_resolve(v, tenant_id, bytes_so_far) for k, v in value.items()}
    if isinstance(value, list):
        return [_walk_and_resolve(v, tenant_id, bytes_so_far) for v in value]
    return value


def resolve_datalab_param_refs(payload: Dict[str, Any], tenant_id: str) -> Dict[str, Any]:
    """
    In-place resolution of $datalab_resultset references in payload.
    Returns a new dict (does not mutate payload). Enforces tenant_id and row/byte limits.
    """
    if not tenant_id:
        return payload
    if not isinstance(payload, dict):
        return payload
    bytes_so_far = [0]
    return _walk_and_resolve(dict(payload), tenant_id, bytes_so_far)
