"""Helpers for tenant/schema (public schema name, schema context no-op for single-schema RLS)."""
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
def schema_context(schema_name: str) -> Iterator[None]:
    """No-op: single schema (public); all tables and RLS use app.current_tenant_slug."""
    yield


# Slug used when no tenant context (RLS policies match no rows)
RLS_NO_TENANT_SLUG = "__none__"


@contextmanager
def tenant_schema_context(tenant_schema: str | None) -> Iterator[None]:
    """Set app.current_tenant_slug for RLS so policies filter in this block (e.g. agent console, Celery)."""
    slug = (str(tenant_schema or "").strip() or RLS_NO_TENANT_SLUG)
    try:
        from django.db import connection
        with connection.cursor() as cursor:
            cursor.execute("SET LOCAL app.current_tenant_slug = %s", [slug])
        yield
    except Exception:
        yield
