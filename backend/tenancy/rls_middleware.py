"""
PostgreSQL Row-Level Security (RLS) middleware.

Sets app.current_tenant_slug for the request so RLS policies filter by tenant slug (subdomain).
El tenant root tiene subdomain = 'platform' y sus filas son visibles para todos.
Safe for async + PgBouncer (SET LOCAL is connection-scoped).
"""
from django.db import connection
from django.utils.deprecation import MiddlewareMixin


# When no tenant, policy (slug = this) matches no row
RLS_NO_TENANT_SLUG = "__none__"


class TenantRLSMiddleware(MiddlewareMixin):
    """Set app.current_tenant_slug for RLS. Run after TenantMiddleware so request.tenant is set."""

    def process_request(self, request):
        tenant = getattr(request, "tenant", None)
        if tenant is not None and getattr(tenant, "pk", None) is not None:
            slug = getattr(tenant, "rls_slug", None) or ""
        else:
            slug = RLS_NO_TENANT_SLUG
        # Nunca null ni vacío: la política RLS asume un valor siempre definido
        if not slug or not str(slug).strip():
            slug = RLS_NO_TENANT_SLUG
        with connection.cursor() as cursor:
            cursor.execute("SET LOCAL app.current_tenant_slug = %s", [str(slug).strip() or RLS_NO_TENANT_SLUG])
