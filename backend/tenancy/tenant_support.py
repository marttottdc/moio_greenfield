"""Helpers for RLS tenant context in the single-schema runtime."""
from __future__ import annotations

import logging
from contextlib import contextmanager
from typing import Iterator

from django.db import connection
from django.db.models import Q
from django_rls.db.functions import get_rls_context

logger = logging.getLogger(__name__)


def tenants_enabled() -> bool:
    """Always False: we use single public schema + RLS, not django-tenants."""
    return False


def public_schema_name() -> str:
    from django.conf import settings
    value = str(getattr(settings, "PUBLIC_SCHEMA_NAME", "public")).strip()
    return value or "public"


def is_public_schema(tenant_schema: str | None) -> bool:
    schema = str(tenant_schema or public_schema_name()).strip().lower()
    return schema == public_schema_name().lower()


def get_public_schema_name() -> str:
    """Alias for public_schema_name (django-tenants compatibility)."""
    return public_schema_name()


@contextmanager
def public_schema_context(schema_name: str) -> Iterator[None]:
    """No-op compatibility helper for code paths that still conceptually target the public space."""
    yield


# Slug used when no tenant context (RLS policies match no rows)
RLS_NO_TENANT_SLUG = "__none__"


def _resolve_tenant_ref(tenant_ref) -> tuple[int | None, str]:
    if tenant_ref is None:
        return None, RLS_NO_TENANT_SLUG

    tenant_id = getattr(tenant_ref, "pk", None)
    tenant_slug = getattr(tenant_ref, "rls_slug", None)
    if tenant_id is not None:
        return tenant_id, (str(tenant_slug or "").strip() or RLS_NO_TENANT_SLUG)

    raw = str(tenant_ref or "").strip()
    if not raw or raw == RLS_NO_TENANT_SLUG:
        return None, RLS_NO_TENANT_SLUG

    try:
        from tenancy.models import Tenant

        tenant = Tenant.objects.only("id", "subdomain", "schema_name").filter(
            Q(subdomain=raw) | Q(schema_name=raw)
        ).first()
        if tenant is not None:
            return tenant.pk, getattr(tenant, "rls_slug", raw)
    except Exception:
        pass

    return None, raw


def get_current_rls_debug_context() -> dict[str, str]:
    """Best-effort snapshot of the active RLS context values."""
    try:
        tenant_id = str(get_rls_context("tenant_id", default="") or "")
    except Exception:
        tenant_id = ""

    legacy_slug = ""
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT current_setting(%s, true)", ["app.current_tenant_slug"])
            row = cursor.fetchone()
            legacy_slug = row[0] if row and row[0] else ""
    except Exception:
        legacy_slug = ""

    return {
        "rls_tenant_id": tenant_id,
        "legacy_tenant_slug": legacy_slug,
    }


def _set_pg_context(setting_name: str, value, *, is_local: bool = False) -> None:
    value = str(value or "")
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT set_config(%s, %s, %s)",
            [setting_name, value, is_local],
        )


def set_current_rls_tenant(tenant_id, *, is_local: bool = False) -> None:
    """Set the active django_rls tenant context."""
    _set_pg_context("rls.tenant_id", tenant_id, is_local=is_local)


def set_current_rls_user(user_id, *, is_local: bool = False) -> None:
    """Set the active django_rls user context."""
    _set_pg_context("rls.user_id", user_id, is_local=is_local)


def set_current_legacy_tenant_slug(slug: str, *, is_local: bool = False) -> None:
    """Set the legacy slug-based RLS context."""
    _set_pg_context("app.current_tenant_slug", slug, is_local=is_local)


def get_table_policies(table_name: str) -> list[dict[str, str]]:
    """Best-effort policy dump for diagnostics."""
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT policyname, cmd, permissive, qual, with_check
                FROM pg_policies
                WHERE schemaname = current_schema()
                  AND tablename = %s
                ORDER BY policyname
                """,
                [table_name],
            )
            rows = cursor.fetchall()
    except Exception:
        return []

    return [
        {
            "policyname": str(row[0] or ""),
            "cmd": str(row[1] or ""),
            "permissive": str(row[2] or ""),
            "qual": str(row[3] or ""),
            "with_check": str(row[4] or ""),
        }
        for row in rows
    ]


@contextmanager
def tenant_rls_context(tenant_slug: str | None) -> Iterator[None]:
    """Set both django_rls and legacy slug context inside this block."""
    tenant_id, slug = _resolve_tenant_ref(tenant_slug)
    previous_tenant_id = ""
    previous_slug = ""
    is_local = bool(getattr(connection, "in_atomic_block", False))
    try:
        try:
            previous_tenant_id = get_rls_context("tenant_id", default="") or ""
        except Exception:
            previous_tenant_id = ""
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT current_setting(%s, true)",
                    ["app.current_tenant_slug"],
                )
                row = cursor.fetchone()
                previous_slug = row[0] if row and row[0] else ""
        except Exception:
            previous_slug = ""

        set_current_rls_tenant(tenant_id, is_local=is_local)
        set_current_legacy_tenant_slug(slug, is_local=is_local)

        debug_context = get_current_rls_debug_context()
        expected_tenant_id = str(tenant_id or "")
        if (
            debug_context.get("rls_tenant_id", "") != expected_tenant_id
            or debug_context.get("legacy_tenant_slug", "") != str(slug)
        ):
            logger.error(
                "RLS context mismatch after set expected_tenant_id=%s expected_slug=%s actual=%s",
                expected_tenant_id,
                slug,
                debug_context,
            )
    except Exception:
        logger.exception(
            "Failed to set tenant RLS context tenant_id=%s slug=%s",
            tenant_id,
            slug,
        )
        raise
    try:
        yield
    finally:
        try:
            set_current_rls_tenant(previous_tenant_id, is_local=is_local)
            set_current_legacy_tenant_slug(previous_slug, is_local=is_local)
        except Exception:
            logger.exception(
                "Failed to restore previous tenant RLS context previous_tenant_id=%s previous_slug=%s",
                previous_tenant_id,
                previous_slug,
            )


# Backward-compatible aliases while the codebase migrates away from schema naming.
schema_context = public_schema_context
tenant_schema_context = tenant_rls_context
