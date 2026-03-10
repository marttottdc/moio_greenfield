"""Helpers for django-tenants (schema context, public schema, etc.)."""
from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator

from django.conf import settings


def tenants_enabled() -> bool:
    return bool(getattr(settings, "DJANGO_TENANTS_ENABLED", False))


def public_schema_name() -> str:
    value = str(getattr(settings, "PUBLIC_SCHEMA_NAME", "public")).strip()
    return value or "public"


def is_public_schema(tenant_schema: str | None) -> bool:
    schema = str(tenant_schema or public_schema_name()).strip().lower()
    return schema == public_schema_name().lower()


@contextmanager
def tenant_schema_context(tenant_schema: str | None) -> Iterator[None]:
    if not tenants_enabled():
        yield
        return

    from django_tenants.utils import schema_context

    schema = str(tenant_schema or public_schema_name()).strip() or public_schema_name()
    with schema_context(schema):
        yield
