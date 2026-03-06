"""
Safe raw SQL executor for Data Lab.

- SELECT only; parameterized only; tenant-scoped; row limit and timeout.
"""
from __future__ import annotations

import re
import logging
from typing import Any

from django.db import connection, transaction

logger = logging.getLogger(__name__)

# Defaults
DEFAULT_ROW_LIMIT = 10_000
DEFAULT_TIMEOUT_SECONDS = 30
TENANT_ID_TOKEN = "{{tenant_id}}"
_TENANT_FILTER_RE = re.compile(
    r"\btenant_id\b\s*=\s*\{\{tenant_id\}\}|\{\{tenant_id\}\}\s*=\s*\btenant_id\b",
    re.IGNORECASE,
)
_PLACEHOLDER_RE = re.compile(r"\{\{tenant_id\}\}|%s")
_SELECT_INTO_RE = re.compile(r"\bSELECT\b[\s\S]*?\bINTO\b", re.IGNORECASE)
_FOR_UPDATE_RE = re.compile(r"\bFOR\s+UPDATE\b", re.IGNORECASE)
_DISALLOWED_SQL_KEYWORDS = (
    "INSERT",
    "UPDATE",
    "DELETE",
    "ALTER",
    "DROP",
    "CREATE",
    "TRUNCATE",
    "MERGE",
    "CALL",
    "DO",
    "COPY",
    "GRANT",
    "REVOKE",
    "VACUUM",
    "ANALYZE",
    "REINDEX",
    "CLUSTER",
    "REFRESH",
)
_DISALLOWED_SQL_RE = re.compile(r"\b(" + "|".join(_DISALLOWED_SQL_KEYWORDS) + r")\b", re.IGNORECASE)


class SafeSQLExecutorError(Exception):
    """Raised when SQL validation or execution fails."""
    pass


def _normalize_sql(sql: str) -> str:
    """Strip comments and normalize whitespace for validation."""
    # Remove single-line comments (-- ...)
    sql = re.sub(r"--[^\n]*", "", sql)
    # Remove multi-line comments (/* ... */)
    sql = re.sub(r"/\*.*?\*/", "", sql, flags=re.DOTALL)
    return " ".join(sql.split()).strip()


def _is_select_only(sql: str) -> bool:
    """Return True if the statement is only a SELECT (no DDL/DML)."""
    normalized = _normalize_sql(sql)
    if not normalized:
        return False

    # Allow one optional trailing semicolon only.
    while normalized.endswith(";"):
        normalized = normalized[:-1].strip()
    if not normalized or ";" in normalized:
        return False

    normalized_upper = normalized.upper()
    if normalized_upper.startswith("WITH "):
        if "SELECT" not in normalized_upper:
            return False
    elif not normalized_upper.startswith("SELECT"):
        return False

    # PostgreSQL SELECT ... INTO creates a table and is not read-only.
    if _SELECT_INTO_RE.search(normalized_upper):
        return False
    if _FOR_UPDATE_RE.search(normalized_upper):
        return False
    if _DISALLOWED_SQL_RE.search(normalized_upper):
        return False
    return True


def _bind_tenant_params(
    sql: str,
    params: list[Any],
    tenant_id: int | None,
) -> tuple[str, list[Any]]:
    """
    Replace tenant placeholders and bind params in SQL order.

    Raw SQL must include an explicit tenant predicate using:
    `tenant_id = {{tenant_id}}` (or the reversed equality).
    """
    if tenant_id is None:
        raise SafeSQLExecutorError("tenant_id is required for raw SQL execution")
    if not _TENANT_FILTER_RE.search(sql):
        raise SafeSQLExecutorError(
            "SQL must include tenant filter using tenant_id = {{tenant_id}}"
        )

    sql_with_db_placeholders = sql.replace(TENANT_ID_TOKEN, "%s")
    final_params: list[Any] = []
    user_param_index = 0
    tenant_bound = False

    for match in _PLACEHOLDER_RE.finditer(sql):
        token = match.group(0)
        if token == TENANT_ID_TOKEN:
            final_params.append(tenant_id)
            tenant_bound = True
            continue
        if user_param_index >= len(params):
            raise SafeSQLExecutorError("SQL placeholders and params length mismatch")
        final_params.append(params[user_param_index])
        user_param_index += 1

    if user_param_index != len(params):
        raise SafeSQLExecutorError("SQL placeholders and params length mismatch")
    if not tenant_bound:
        raise SafeSQLExecutorError(
            "SQL must include tenant filter using tenant_id = {{tenant_id}}"
        )

    return sql_with_db_placeholders, final_params


class SafeSQLExecutor:
    """
    Execute read-only, parameterized SQL with tenant scope, row limit, and timeout.
    """

    def __init__(
        self,
        row_limit: int = DEFAULT_ROW_LIMIT,
        timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
    ):
        self.row_limit = row_limit
        self.timeout_seconds = timeout_seconds

    def execute(
        self,
        sql: str,
        params: list[Any] | tuple[Any, ...] | None = None,
        tenant_id: int | None = None,
        row_limit: int | None = None,
    ) -> list[dict[str, Any]]:
        """
        Execute a single SELECT statement and return rows as list of dicts.

        Args:
            sql: Parameterized SQL (use %s for placeholders).
            params: Query parameters (e.g. [tenant_id, start_date]).
            tenant_id: Current tenant id used to bind {{tenant_id}} placeholders.
            row_limit: Override instance row_limit for this call.

        Returns:
            List of dicts (one per row), keys = column names.

        Raises:
            SafeSQLExecutorError: If SQL is not SELECT-only or execution fails.
        """
        if not _is_select_only(sql):
            raise SafeSQLExecutorError("Only SELECT (and WITH ... SELECT) statements are allowed")

        params = list(params) if params is not None else []
        sql, bound_params = _bind_tenant_params(sql, params, tenant_id)
        limit = row_limit if row_limit is not None else self.row_limit

        with transaction.atomic():
            with connection.cursor() as cursor:
                try:
                    # SET LOCAL only applies for the current transaction.
                    cursor.execute(
                        "SET LOCAL statement_timeout = %s",
                        [f"{self.timeout_seconds}s"],
                    )
                except Exception as e:
                    logger.warning("Could not set statement_timeout: %s", e)
                    # Continue without timeout (e.g. SQLite)

                cursor.execute(sql, bound_params)
                columns = [col[0] for col in cursor.description] if cursor.description else []
                rows = cursor.fetchmany(limit)
                return [dict(zip(columns, row)) for row in rows]
