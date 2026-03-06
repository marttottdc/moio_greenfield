"""
Query engine runner: run query (CRM or SQL) + optional post_process, or run snippet with ctx.
"""
from __future__ import annotations

import logging
from typing import Any

from django.db.models import Q

from datalab.core.serialization import serialize_for_json
from datalab.crm_sources.models import CRMView
from datalab.crm_sources.orm_builder import CRMQueryORMBuilder, CRMQueryORMBuilderError
from datalab.query_engine.sandbox import run_sandboxed_code, SandboxError
from datalab.query_engine.sql_executor import SafeSQLExecutor, SafeSQLExecutorError

logger = logging.getLogger(__name__)

# Limits
DEFAULT_QUERY_ROW_LIMIT = 10_000
SANDBOX_TIMEOUT_SECONDS = 30


class QueryEngineError(Exception):
    """Raised when query execution or code execution fails."""
    pass


def _run_crm_view(
    view_key: str,
    tenant: Any,
    filters: dict[str, Any] | None,
    limit: int,
) -> list[dict[str, Any]]:
    """Execute a CRM view and return list of dicts."""
    try:
        view = CRMView.objects.get(
            (Q(tenant=tenant) | Q(is_global=True)),
            key=view_key,
            is_active=True,
        )
    except CRMView.DoesNotExist:
        raise QueryEngineError(f"CRMView '{view_key}' not found for tenant")

    if filters and view.allowed_filters_json:
        invalid = [k for k in filters if k not in view.allowed_filters_json]
        if invalid:
            raise QueryEngineError(f"Invalid filters: {invalid}. Allowed: {view.allowed_filters_json}")

    builder = CRMQueryORMBuilder()
    try:
        df = builder.build_queryset(view, filters)
    except CRMQueryORMBuilderError as e:
        raise QueryEngineError(f"CRM query failed: {e}") from e

    df = df.head(limit)
    records = df.to_dict(orient="records")
    return serialize_for_json(records) or []


def _run_sql(
    sql: str,
    params: list[Any] | None,
    tenant_id: int,
    row_limit: int,
) -> list[dict[str, Any]]:
    """Execute safe raw SQL and return list of dicts."""
    executor = SafeSQLExecutor(row_limit=row_limit, timeout_seconds=SANDBOX_TIMEOUT_SECONDS)
    try:
        return executor.execute(sql, params or [], tenant_id=tenant_id, row_limit=row_limit)
    except SafeSQLExecutorError as e:
        raise QueryEngineError(f"SQL execution failed: {e}") from e


def run_query(
    query: dict[str, Any],
    tenant: Any,
    row_limit: int = DEFAULT_QUERY_ROW_LIMIT,
) -> list[dict[str, Any]]:
    """
    Run a single query (CRM view or raw SQL) and return rows as list of dicts.

    query: {"type": "crm_view", "view_key": "...", "filters": {...}}
           or {"type": "sql", "sql": "SELECT ...", "params": [...]}
    """
    qtype = query.get("type")
    if qtype == "crm_view":
        return _run_crm_view(
            view_key=query["view_key"],
            tenant=tenant,
            filters=query.get("filters"),
            limit=row_limit,
        )
    if qtype == "sql":
        sql = query.get("sql")
        if not sql:
            raise QueryEngineError("query.sql is required for type 'sql'")
        params = query.get("params")
        if params is None:
            params = []
        return _run_sql(sql, params, tenant_id=tenant.pk, row_limit=row_limit)
    raise QueryEngineError(f"Unknown query type: {qtype}")


def _make_ctx(tenant: Any, row_limit: int) -> Any:
    """Build context object with run_sql and run_view for snippets."""

    class _Ctx:
        def __init__(self, tenant: Any, limit: int):
            self._tenant = tenant
            self._limit = limit
            self.tenant_id = getattr(tenant, "pk", getattr(tenant, "id", None))

        def run_sql(self, sql: str, params: list[Any] | None = None) -> list[dict[str, Any]]:
            return _run_sql(sql, params or [], self._tenant.pk, self._limit)

        def run_view(
            self,
            view_key: str,
            filters: dict[str, Any] | None = None,
        ) -> list[dict[str, Any]]:
            return _run_crm_view(view_key, self._tenant, filters, self._limit)

    return _Ctx(tenant, row_limit)


class QueryEngineRunner:
    """
    Run queries (CRM or SQL) with optional post-processing code, or run snippets with ctx.
    """

    def __init__(
        self,
        row_limit: int = DEFAULT_QUERY_ROW_LIMIT,
        sandbox_timeout: int = SANDBOX_TIMEOUT_SECONDS,
    ):
        self.row_limit = row_limit
        self.sandbox_timeout = sandbox_timeout

    def execute_query_and_post_process(
        self,
        query: dict[str, Any],
        post_process_code: str | None,
        tenant: Any,
        user: Any = None,
    ) -> Any:
        """
        Run query, then optionally run post_process_code(result); return final value.

        post_process_code may define run(result) or main(result); it receives
        the query result as list of dicts. If pandas is needed, inject it in sandbox (future).
        """
        result = run_query(query, tenant, row_limit=self.row_limit)

        if not post_process_code or not post_process_code.strip():
            return result

        globals_inject = {"result": result}
        try:
            return run_sandboxed_code(
                post_process_code,
                globals_inject,
                timeout_seconds=self.sandbox_timeout,
            )
        except SandboxError as e:
            raise QueryEngineError(f"Post-processing failed: {e}") from e

    def execute_snippet(
        self,
        code: str,
        tenant: Any,
        user: Any = None,
    ) -> Any:
        """
        Run a Python snippet with ctx.run_sql and ctx.run_view available.
        Snippet should return a JSON-serializable value (or define run()/main()).
        """
        ctx = _make_ctx(tenant, self.row_limit)
        globals_inject = {"ctx": ctx}
        try:
            return run_sandboxed_code(
                code,
                globals_inject,
                timeout_seconds=self.sandbox_timeout,
            )
        except SandboxError as e:
            raise QueryEngineError(f"Snippet execution failed: {e}") from e
