"""Tenant resolution middleware."""
from django.contrib.auth import get_user_model

from tenancy.context_utils import current_tenant

try:
    from django_tenants.utils import get_public_schema_name
except Exception:  # pragma: no cover
    get_public_schema_name = None


class TenantMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = request.user if request.user.is_authenticated else None
        tenant = getattr(request, "tenant", None)
        public_schema = get_public_schema_name() if get_public_schema_name else "public"
        if (
            tenant is None
            or getattr(tenant, "schema_name", public_schema) == public_schema
        ):
            tenant = getattr(user, "tenant", None)

        token = current_tenant.set(tenant)
        try:
            response = self.get_response(request)
        finally:
            current_tenant.reset(token)
        return response
