"""Helpers for RLS tenant context in the single-schema runtime."""
from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator


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


@contextmanager
def tenant_rls_context(tenant_slug: str | None) -> Iterator[None]:
    """Set `app.current_tenant_slug` so RLS policies operate within this block."""
    slug = (str(tenant_slug or "").strip() or RLS_NO_TENANT_SLUG)
    try:
        from django.db import connection
        with connection.cursor() as cursor:
            cursor.execute("SET LOCAL app.current_tenant_slug = %s", [slug])
    except Exception:
        # If the RLS setup itself fails, continue without injecting tenant context.
        # Do not swallow exceptions raised inside the wrapped block.
        pass
    yield


# Backward-compatible aliases while the codebase migrates away from schema naming.
schema_context = public_schema_context
tenant_schema_context = tenant_rls_context
