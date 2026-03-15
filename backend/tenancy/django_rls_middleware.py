from __future__ import annotations

import logging

from django.db import transaction
from django.http import JsonResponse
from rest_framework import authentication
from rest_framework.settings import api_settings

from tenancy.resolution import (
    bind_request_tenant,
    ensure_request_tenant_context,
    route_policy_for_request,
    route_requires_tenant,
)
from tenancy.tenant_support import (
    RLS_NO_TENANT_SLUG,
    set_current_legacy_tenant_slug,
    set_current_rls_tenant,
    set_current_rls_user,
)

logger = logging.getLogger(__name__)


def _run_drf_auth(request) -> None:
    """Populate request.user/request.auth before DRF views run."""
    for auth_cls in getattr(api_settings, "DEFAULT_AUTHENTICATION_CLASSES", ()):
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


class MoioRLSContextMiddleware:
    """
    Transaction-scoped RLS middleware compatible with PgBouncer transaction pooling.

    For tenant/optional routes we authenticate early when needed, resolve/bind
    the effective tenant, and set both the django_rls and legacy slug contexts
    with SET LOCAL semantics inside a single request transaction.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        route_policy = route_policy_for_request(request)
        if route_policy in {"public", "external"}:
            return self.get_response(request)

        with transaction.atomic():
            self._prepare_request_context(request, route_policy)
            self._set_local_rls_context(request)

            if route_requires_tenant(request) and getattr(request, "tenant", None) is None:
                return JsonResponse(
                    {"detail": "Tenant context is required for this endpoint."},
                    status=403,
                )

            return self.get_response(request)

    def _prepare_request_context(self, request, route_policy: str) -> None:
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
                    route_policy=route_policy,
                )
            else:
                ensure_request_tenant_context(
                    request,
                    user=user,
                    require_tenant=False,
                )
        except Exception:
            logger.exception("Failed to prepare request tenant context path=%s", getattr(request, "path", ""))

    def _set_local_rls_context(self, request) -> None:
        tenant = getattr(request, "tenant", None) or getattr(getattr(request, "user", None), "tenant", None)
        user = getattr(request, "user", None)

        tenant_id = getattr(tenant, "pk", None) or ""
        tenant_slug = getattr(tenant, "rls_slug", None) or RLS_NO_TENANT_SLUG
        user_id = getattr(user, "pk", None) if getattr(user, "is_authenticated", False) else ""

        set_current_rls_tenant(tenant_id, is_local=True)
        set_current_rls_user(user_id, is_local=True)
        set_current_legacy_tenant_slug(str(tenant_slug), is_local=True)
