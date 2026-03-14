"""Tenant resolution middleware."""

from django.conf import settings

from tenancy.context_utils import current_tenant
from tenancy.resolution import (
    activate_public_schema,
    attach_tenant_to_request,
    resolve_request_tenant,
    activate_tenant,
)

USE_RLS = getattr(settings, "USE_RLS_TENANCY", False)


class TenantMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = getattr(request, "user", None)
        if not getattr(user, "is_authenticated", False):
            user = None
        resolution = resolve_request_tenant(request, user=user)
        tenant = resolution.tenant
        attach_tenant_to_request(
            request,
            tenant,
            user=user,
            source=resolution.source,
            route_policy=resolution.route_policy,
        )
        token = current_tenant.set(tenant)
        if not USE_RLS:
            activate_tenant(tenant)
        try:
            response = self.get_response(request)
        finally:
            if not USE_RLS:
                activate_public_schema()
            current_tenant.reset(token)
        return response
