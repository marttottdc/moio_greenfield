"""
API view for Data Lab execute: query + optional post_process, or snippet.
"""
from __future__ import annotations

import logging
from typing import Any

from rest_framework import status
from rest_framework.response import Response
from drf_spectacular.utils import extend_schema

from datalab.api.views import AuthenticatedDataLabView
from datalab.core.models import ResultSet, ResultSetOrigin, ResultSetStorage
from datalab.core.serialization import serialize_for_json
from datalab.query_engine.runner import QueryEngineRunner, QueryEngineError
from moio_platform.api_schemas import Tags

from . import serializers

logger = logging.getLogger(__name__)

PREVIEW_LIMIT = 200


def _infer_schema(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Infer schema_json from list of dicts (first row keys, type string)."""
    if not rows:
        return []
    keys = list(rows[0].keys()) if rows[0] else []
    return [{"name": k, "type": "string", "nullable": True} for k in keys]


def _persist_result(
    result: list[dict[str, Any]],
    tenant: Any,
    user: Any,
    lineage: dict[str, Any],
) -> ResultSet:
    """Create a ResultSet from execute result (list of rows)."""
    schema = _infer_schema(result)
    preview = serialize_for_json(result[:PREVIEW_LIMIT]) if result else []
    return ResultSet.objects.create(
        tenant=tenant,
        origin=ResultSetOrigin.SCRIPT,
        schema_json=schema,
        row_count=len(result),
        storage=ResultSetStorage.MEMORY,
        preview_json=preview,
        lineage_json=lineage,
        created_by=user,
    )


def _coerce_jsonable(value):
    """Ensure value is JSON-serializable (for response)."""
    import json
    try:
        json.dumps(value)
        return value
    except (TypeError, ValueError):
        if isinstance(value, dict):
            return {str(k): _coerce_jsonable(v) for k, v in value.items()}
        if isinstance(value, (list, tuple)):
            return [_coerce_jsonable(v) for v in value]
        return str(value)


class ExecuteView(AuthenticatedDataLabView):
    """
    Execute a query (with optional post-processing) or a snippet.

    - Query + post_process: POST body { "query": { "type": "crm_view"|"sql", ... }, "post_process_code": "..." }
    - Snippet: POST body { "code": "..." } (ctx.run_sql, ctx.run_view available)
    """

    runner = QueryEngineRunner()

    @extend_schema(
        tags=[Tags.DATALAB_EXECUTE],
        request=serializers.ExecuteRequestSerializer,
        responses={
            200: serializers.ExecuteResponseSerializer,
            400: {"description": "Invalid request or execution error"},
        },
    )
    def post(self, request):
        tenant = self.get_tenant(request)
        ser = serializers.ExecuteRequestSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        data = ser.validated_data

        try:
            if data.get("code", "").strip():
                result = self.runner.execute_snippet(
                    code=data["code"],
                    tenant=tenant,
                    user=request.user,
                )
                result = _coerce_jsonable(result)
                row_count = len(result) if isinstance(result, list) else None
                payload = {"result": result}
                if row_count is not None:
                    payload["row_count"] = row_count
                if data.get("persist") and isinstance(result, list) and result and isinstance(result[0], dict):
                    rs = _persist_result(
                        result, tenant, request.user,
                        lineage={"source": "execute_snippet"},
                    )
                    payload["resultset_id"] = str(rs.id)
                return Response(payload, status=status.HTTP_200_OK)

            query = data["query"]
            post_process_code = (data.get("post_process_code") or "").strip()
            result = self.runner.execute_query_and_post_process(
                query=query,
                post_process_code=post_process_code or None,
                tenant=tenant,
                user=request.user,
            )
            result = _coerce_jsonable(result)
            row_count = len(result) if isinstance(result, list) else None
            payload = {"result": result}
            if row_count is not None:
                payload["row_count"] = row_count
            if data.get("persist") and isinstance(result, list) and result and isinstance(result[0], dict):
                rs = _persist_result(
                    result, tenant, request.user,
                    lineage={"source": "execute_query", "query_type": query.get("type")},
                )
                payload["resultset_id"] = str(rs.id)
            return Response(payload, status=status.HTTP_200_OK)
        except QueryEngineError as e:
            logger.warning("Data Lab execute failed: %s", e)
            return Response(
                {"error": "Execution failed", "details": str(e)},
                status=status.HTTP_400_BAD_REQUEST,
            )
        except Exception as e:
            logger.exception("Data Lab execute error")
            return Response(
                {"error": "Execution failed", "details": str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )
