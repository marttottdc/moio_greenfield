"""
PostgreSQL Row-Level Security (RLS) middleware.

Central point: resolve tenant and set app.current_tenant_slug for the request so RLS
policies filter by tenant slug. Public/external routes get slug __none__ and skip auth.
Tenant/optional routes run DRF auth then resolve + bind tenant (and set slug).
Safe for async + PgBouncer (SET LOCAL is connection-scoped).
"""
import logging

from django.db import connection
from django.utils.deprecation import MiddlewareMixin

from tenancy.resolution import (
    route_policy_for_request,
    route_requires_tenant,
    ensure_request_tenant_context,
    bind_request_tenant,
)

_log = logging.getLogger("tenancy.rls_middleware")

# When no tenant, policy (slug = this) matches no row
RLS_NO_TENANT_SLUG_VALUE = "__none__"
RLS_BYPASS_PATHS = {"/health", "/health/", "/api/v1/health/"}


def _set_rls_slug(slug: str) -> None:
    slug = (str(slug or "").strip() or RLS_NO_TENANT_SLUG_VALUE)
    try:
        with connection.cursor() as cursor:
            cursor.execute("SET LOCAL app.current_tenant_slug = %s", [slug])
    except Exception:
        pass


def _run_drf_auth(request):
    """Run DRF default authentication to set request.user (and request.auth) when possible."""
    from rest_framework import authentication
    from rest_framework.settings import api_settings

    auth_classes = getattr(api_settings, "DEFAULT_AUTHENTICATION_CLASSES", ())
    for auth_cls in auth_classes:
        if not isinstance(auth_cls, type):
            continue
        try:
            instance = auth_cls()
            if not isinstance(instance, authentication.BaseAuthentication):
                continue
            result = instance.authenticate(request)
            if result is not None:
                request.user = result[0]
                request.auth = result[1] if len(result) > 1 else None
                return
        except Exception:
            continue


class TenantAndRLSMiddleware(MiddlewareMixin):
    """
    Single central middleware for tenant + RLS.

    - public/external: set app.current_tenant_slug = __none__, no auth.
    - tenant/optional: run DRF auth, then resolve tenant and set request.tenant
      and app.current_tenant_slug via ensure_request_tenant_context (bind_request_tenant).
    Run after TenantMiddleware and AuthenticationMiddleware.
    """

    def process_request(self, request):
        path = getattr(request, "path_info", "") or getattr(request, "path", "") or ""
        if path in RLS_BYPASS_PATHS:
            _set_rls_slug(RLS_NO_TENANT_SLUG_VALUE)
            return

        policy = route_policy_for_request(request)

        if policy in ("public", "external"):
            _set_rls_slug(RLS_NO_TENANT_SLUG_VALUE)
            return

        # tenant or optional: run auth so request.user is set, then resolve + bind (sets slug)
        _run_drf_auth(request)
        user = getattr(request, "user", None)
        auth = getattr(request, "auth", None)
        try:
            if auth is not None and getattr(auth, "tenant", None) is not None:
                bind_request_tenant(
                    request,
                    auth.tenant,
                    user=user,
                    source="api_key",
                    route_policy=policy,
                )
            else:
                ensure_request_tenant_context(
                    request,
                    user=user,
                    require_tenant=False,
                )
        except Exception:
            pass
        # Ensure slug is set even when no tenant (optional route)
        tenant = getattr(request, "tenant", None)
        if tenant is not None and getattr(tenant, "pk", None) is not None:
            slug = getattr(tenant, "rls_slug", None) or ""
        else:
            slug = RLS_NO_TENANT_SLUG_VALUE
        if not slug or not str(slug).strip():
            slug = RLS_NO_TENANT_SLUG_VALUE
        _set_rls_slug(slug)

        if route_requires_tenant(request) and getattr(request, "tenant", None) is None:
            from django.http import JsonResponse
            return JsonResponse(
                {"detail": "Tenant context is required for this endpoint."},
                status=403,
            )


class TenantRLSMiddleware(MiddlewareMixin):
    """
    Legacy: only sets app.current_tenant_slug from request.tenant.
    Prefer TenantAndRLSMiddleware which resolves tenant + sets slug centrally.
    """

    def process_request(self, request):
        if getattr(request, "path_info", "") in RLS_BYPASS_PATHS:
            return

        tenant = getattr(request, "tenant", None)
        if tenant is not None and getattr(tenant, "pk", None) is not None:
            slug = getattr(tenant, "rls_slug", None) or ""
        else:
            slug = RLS_NO_TENANT_SLUG_VALUE
        if not slug or not str(slug).strip():
            slug = RLS_NO_TENANT_SLUG_VALUE
        _set_rls_slug(slug)
