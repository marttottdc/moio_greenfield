"""Helpers for RLS tenant context in the single-schema runtime."""
from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator

from django.db import connection
from django.db.models import Q
from django_rls.db.functions import get_rls_context, set_rls_context


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


@contextmanager
def tenant_rls_context(tenant_slug: str | None) -> Iterator[None]:
    """Set both django_rls and legacy slug context inside this block."""
    tenant_id, slug = _resolve_tenant_ref(tenant_slug)
    previous_tenant_id = ""
    previous_slug = ""
    try:
        previous_tenant_id = get_rls_context("tenant_id", default="") or ""
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT current_setting(%s, true)",
                ["app.current_tenant_slug"],
            )
            row = cursor.fetchone()
            previous_slug = row[0] if row and row[0] else ""
        set_rls_context("tenant_id", tenant_id or "", is_local=False)
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT set_config(%s, %s, %s)",
                ["app.current_tenant_slug", slug, False],
            )
    except Exception:
        # If the RLS setup itself fails, continue without injecting tenant context.
        # Do not swallow exceptions raised inside the wrapped block.
        pass
    try:
        yield
    finally:
        try:
            set_rls_context("tenant_id", previous_tenant_id, is_local=False)
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT set_config(%s, %s, %s)",
                    ["app.current_tenant_slug", previous_slug, False],
                )
        except Exception:
            pass


# Backward-compatible aliases while the codebase migrates away from schema naming.
schema_context = public_schema_context
tenant_schema_context = tenant_rls_context
