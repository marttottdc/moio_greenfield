"""Canonical tenant resolution helpers for HTTP request boundaries."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from django.conf import settings

from tenancy.context_utils import current_tenant
from tenancy.tenant_support import public_schema_name


def _current_connection_schema() -> str:
    """Return the active DB schema name for trace logging."""
    try:
        from django.db import connection
        return str(getattr(connection, "schema_name", "?") or "?")
    except Exception:
        return "?"

RoutePolicy = Literal["public", "external", "tenant", "optional"]

_PUBLIC_EXACT_PATHS = {
    "/health",
    "/health/",
    "/api/v1/health/",
    "/api/v1/meta/endpoints/",
    "/api/schema/",
    "/api/v1/test/",
    "/api/v1/auth/login",
    "/api/v1/auth/login/",
    "/api/v1/auth/refresh",
    "/api/v1/auth/refresh/",
}

_PUBLIC_PREFIXES = (
    "/api/docs/",
    "/api/platform/",
)

# No trailing slash so both /path and /path/ match (e.g. Shopify embed bootstrap)
_EXTERNAL_PREFIXES = (
    "/webhooks/",
    "/api/v1/tenants/",
    "/api/v1/integrations/shopify/oauth",
    "/api/v1/integrations/shopify/webhook",
    "/api/v1/integrations/shopify/embed/bootstrap",
    "/api/v1/integrations/shopify/chat-widget-config",
    "/api/v1/integrations/shopify/app-proxy",
    "/api/v1/integrations/whatsapp/embedded-signup",
)

_TENANT_REQUIRED_PREFIXES = (
    "/api/tenant/",
    "/api/v1/bootstrap/",
    "/api/v1/content/",
    "/api/v1/users/",
    "/api/v1/settings/",
    "/api/v1/crm/",
    "/api/v1/activities/",
    "/api/v1/capture/",
    "/api/v1/timeline/",
    "/api/v1/resources/",
    "/api/v1/campaigns/",
    "/api/v1/flows/",
    "/api/v1/scripts/",
    "/api/v1/desktop-agent/",
    "/api/v1/datalab/",
    "/api/v1/integrations/",
)

_OPTIONAL_PREFIXES = (
    "/api/v1/auth/me",
    "/api/v1/auth/logout",
    "/api/v1/auth/api-key",
)

_GENERIC_HOSTS = {"", "localhost", "127.0.0.1"}


@dataclass(frozen=True)
class TenantResolution:
    tenant: object | None
    source: str | None
    route_policy: RoutePolicy


class TenantResolutionError(ValueError):
    """Raised when a tenant-scoped request cannot be resolved safely."""


def _normalized_path(request_or_path) -> str:
    if hasattr(request_or_path, "path_info"):
        path = getattr(request_or_path, "path_info", "") or getattr(request_or_path, "path", "")
    else:
        path = str(request_or_path or "")
    normalized = "/" + str(path or "").lstrip("/")
    return normalized or "/"


def route_policy_for_request(request_or_path) -> RoutePolicy:
    path = _normalized_path(request_or_path)
    if path in _PUBLIC_EXACT_PATHS:
        return "public"
    if any(path.startswith(prefix) for prefix in _PUBLIC_PREFIXES):
        return "public"
    if any(path.startswith(prefix) for prefix in _EXTERNAL_PREFIXES):
        return "external"
    if any(path.startswith(prefix) for prefix in _OPTIONAL_PREFIXES):
        return "optional"
    if any(path.startswith(prefix) for prefix in _TENANT_REQUIRED_PREFIXES):
        return "tenant"
    return "optional"


def route_requires_tenant(request_or_path) -> bool:
    return route_policy_for_request(request_or_path) == "tenant"


def _tenant_has_schema(tenant) -> bool:
    schema_name = str(getattr(tenant, "schema_name", "") or "").strip().lower()
    return bool(schema_name and schema_name != public_schema_name().lower())


def _run_in_public_schema(loader):
    from tenancy.tenant_support import public_schema_context
    with public_schema_context(public_schema_name()):
        return loader()


def _load_tenant_from_schema(schema_name: str | None):
    schema = str(schema_name or "").strip().lower()
    if not schema or schema == public_schema_name().lower():
        return None

    from tenancy.models import Tenant

    return _run_in_public_schema(lambda: Tenant.objects.filter(schema_name=schema).first())


def _host_without_port(request) -> str:
    host = str(request.META.get("HTTP_HOST", "") or "").strip().lower()
    return host.split(":", 1)[0]


def resolve_tenant_from_host(request):
    host = _host_without_port(request)
    if host in _GENERIC_HOSTS:
        return None

    def _lookup():
        from tenancy.models import Tenant, TenantDomain

        domain_match = TenantDomain.objects.select_related("tenant").filter(domain=host).first()
        if domain_match is not None:
            return getattr(domain_match, "tenant", None)

        parts = host.split(".")
        if len(parts) >= 3:
            subdomain = parts[0]
            domain = ".".join(parts[1:])
            return Tenant.objects.filter(subdomain=subdomain, domain=domain).first()

        return Tenant.objects.filter(domain=host, subdomain__isnull=True).first()

    return _run_in_public_schema(_lookup)


def resolve_tenant_from_jwt(request):
    from tenancy.host_rewrite import _get_tenant_schema_from_jwt

    return _load_tenant_from_schema(_get_tenant_schema_from_jwt(request))


def resolve_tenant_from_user(user):
    tenant = getattr(user, "tenant", None) if user is not None else None
    if _tenant_has_schema(tenant):
        return tenant

    tenant_id = getattr(user, "tenant_id", None) if user is not None else None
    if not tenant_id:
        return None

    def _lookup():
        from tenancy.models import Tenant

        return Tenant.objects.filter(pk=tenant_id).first()

    tenant = _run_in_public_schema(_lookup)
    return tenant if _tenant_has_schema(tenant) else None


def resolve_request_tenant(request, *, user=None) -> TenantResolution:
    # Temporary: skip resolution and treat all requests as external (no tenant)
    if getattr(settings, "DISABLE_TENANT_RESOLUTION", False):
        return TenantResolution(tenant=None, source=None, route_policy="external")

    route_policy = route_policy_for_request(request)
    if route_policy in {"public", "external"}:
        return TenantResolution(tenant=None, source=None, route_policy=route_policy)

    # For authenticated API traffic behind shared hosts/proxies, JWT and user context
    # are more reliable than the incoming Host header.
    tenant = resolve_tenant_from_jwt(request)
    if _tenant_has_schema(tenant):
        return TenantResolution(tenant=tenant, source="jwt", route_policy=route_policy)

    tenant = resolve_tenant_from_user(user)
    if _tenant_has_schema(tenant):
        return TenantResolution(tenant=tenant, source="user", route_policy=route_policy)

    tenant = resolve_tenant_from_host(request)
    if _tenant_has_schema(tenant):
        return TenantResolution(tenant=tenant, source="host", route_policy=route_policy)

    return TenantResolution(tenant=None, source=None, route_policy=route_policy)


def attach_tenant_to_request(
    request,
    tenant,
    *,
    user=None,
    source: str | None = None,
    route_policy: RoutePolicy | None = None,
):
    setattr(request, "tenant", tenant)
    setattr(request, "tenant_resolution_source", source)
    setattr(request, "tenant_route_policy", route_policy or route_policy_for_request(request))

    if user is not None and tenant is not None:
        try:
            setattr(user, "tenant", tenant)
            setattr(user, "tenant_id", getattr(tenant, "pk", None))
        except Exception:
            pass


def activate_public_schema() -> None:
    if not getattr(settings, "DJANGO_TENANTS_ENABLED", False):
        return
    try:
        from django.db import connection

        if hasattr(connection, "set_schema_to_public"):
            connection.set_schema_to_public()
            return
        if hasattr(connection, "set_schema"):
            connection.set_schema(public_schema_name())
    except Exception:
        pass


def activate_tenant(tenant) -> None:
    if not getattr(settings, "DJANGO_TENANTS_ENABLED", False):
        return
    try:
        from django.db import connection

        if _tenant_has_schema(tenant):
            connection.set_tenant(tenant)
        else:
            activate_public_schema()
    except Exception:
        pass


def bind_request_tenant(
    request,
    tenant,
    *,
    user=None,
    source: str | None = None,
    route_policy: RoutePolicy | None = None,
) -> None:
    attach_tenant_to_request(
        request,
        tenant,
        user=user,
        source=source,
        route_policy=route_policy,
    )
    current_tenant.set(tenant)
    activate_tenant(tenant)


def ensure_request_tenant_context(request, *, user=None, require_tenant: bool | None = None):
    resolution = resolve_request_tenant(request, user=user)
    bind_request_tenant(
        request,
        resolution.tenant,
        user=user,
        source=resolution.source,
        route_policy=resolution.route_policy,
    )
    must_have_tenant = route_requires_tenant(request) if require_tenant is None else bool(require_tenant)
    if must_have_tenant and resolution.tenant is None:
        raise TenantResolutionError("Tenant context is required for this endpoint.")
    return resolution.tenant
