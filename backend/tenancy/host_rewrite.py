"""Host rewrite middleware for tenant resolution from JWT.

When requests hit the backend with a generic Host (localhost, 127.0.0.1), e.g. when
the frontend proxies to the same backend URL, tenant resolution by host loses the
original tenant domain. This middleware rewrites HTTP_HOST to the tenant's primary
domain when a valid JWT tenant_schema claim is present. No frontend changes needed.
"""
import re

from rest_framework_simplejwt.exceptions import InvalidToken
from rest_framework_simplejwt.tokens import AccessToken

from tenancy.tenant_support import public_schema_name

# RFC 1034/1035: schema names use same rules as subdomain (letters, digits, hyphens)
_SCHEMA_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,61}[a-z0-9]?$", re.IGNORECASE)


def _is_generic_host(host: str) -> bool:
    """Return True if host is localhost or 127.0.0.1 (optionally with port)."""
    hostname = host.split(":")[0].strip().lower()
    return hostname in ("localhost", "127.0.0.1")


def _valid_schema(value: str) -> str | None:
    """Return normalized schema name if valid, else None."""
    if not value or not isinstance(value, str):
        return None
    s = value.strip().lower()
    if not s or s == "public":
        return None
    if _SCHEMA_RE.match(s):
        return s
    return None


def _get_tenant_schema_from_jwt(request) -> str | None:
    """Extract and validate JWT, return tenant_schema from payload or None."""
    auth_header = request.META.get("HTTP_AUTHORIZATION")
    if not auth_header or not auth_header.startswith("Bearer "):
        return None
    raw_token = auth_header[7:].strip()
    if not raw_token:
        return None
    try:
        token = AccessToken(raw_token)
        schema = token.get("tenant_schema")
        return _valid_schema(str(schema)) if schema else None
    except (InvalidToken, Exception):
        return None


def _tenant_host_from_schema(schema_name: str | None) -> str | None:
    schema = _valid_schema(str(schema_name or ""))
    if not schema:
        return None
    try:
        from tenancy.models import Tenant
        from tenancy.tenant_support import schema_context

        with schema_context(public_schema_name()):
            tenant = Tenant.objects.filter(schema_name=schema).first()
    except Exception:
        try:
            from tenancy.models import Tenant
            tenant = Tenant.objects.filter(schema_name=schema).first()
        except Exception:
            tenant = None
    if tenant is None:
        return None
    host = str(getattr(tenant, "primary_domain", "") or "").strip().lower()
    return host or None


class HostRewriteFromJWTMiddleware:
    """Rewrite HTTP_HOST from JWT tenant_schema when Host is generic (localhost/127.0.0.1)."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        host_header = request.META.get("HTTP_HOST", "")

        if _is_generic_host(host_header):
            tenant_schema = _get_tenant_schema_from_jwt(request)
            if tenant_schema:
                new_host = _tenant_host_from_schema(tenant_schema)
                if not new_host:
                    port_part = ""
                    if ":" in host_header:
                        port_part = ":" + host_header.split(":")[-1]
                    new_host = f"{tenant_schema}.127.0.0.1{port_part}"
                request.META["HTTP_HOST"] = new_host

        return self.get_response(request)
