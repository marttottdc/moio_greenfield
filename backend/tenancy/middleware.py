"""Tenant resolution middleware. JWT primary; no subdomain/host-based resolution."""
from django.conf import settings

from tenancy.context_utils import current_tenant


def _resolve_tenant_from_jwt(request):
    """Resolve tenant from JWT tenant_schema claim. Primary method for tenant resolution."""
    from tenancy.host_rewrite import _get_tenant_schema_from_jwt
    from tenancy.models import Tenant
    from tenancy.tenant_support import public_schema_name

    schema_name = _get_tenant_schema_from_jwt(request)
    if not schema_name:
        return None

    try:
        from django_tenants.utils import schema_context

        with schema_context(public_schema_name()):
            return Tenant.objects.filter(schema_name=schema_name).first()
    except Exception:
        return Tenant.objects.filter(schema_name=schema_name).first()


class TenantMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # Primary: JWT tenant_schema (set at login, available before DRF auth).
        tenant = _resolve_tenant_from_jwt(request)

        # Fallback: user.tenant when already loaded (e.g. session auth).
        if tenant is None and request.user.is_authenticated:
            tenant = getattr(request.user, "tenant", None)

        # Switch DB connection to tenant schema when tenant-scoped models
        # (e.g. crm_activityrecord) are needed. Always set when we have a tenant,
        # not only when on public: connections are reused and may retain a previous
        # request's schema.
        if (
            tenant
            and getattr(tenant, "schema_name", None)
            and getattr(settings, "DJANGO_TENANTS_ENABLED", False)
        ):
            try:
                from django.db import connection

                connection.set_tenant(tenant)
            except Exception:
                pass

        token = current_tenant.set(tenant)
        try:
            response = self.get_response(request)
        finally:
            current_tenant.reset(token)
        return response
