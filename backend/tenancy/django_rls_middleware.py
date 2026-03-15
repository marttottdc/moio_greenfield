from __future__ import annotations

from django.db import connection
from django_rls.db.functions import set_rls_context
from django_rls.middleware import RLSContextMiddleware

from tenancy.tenant_support import RLS_NO_TENANT_SLUG


class MoioRLSContextMiddleware(RLSContextMiddleware):
    """
    Bridge middleware for the migration from slug-based RLS to django_rls.

    It sets the new `rls.tenant_id` / `rls.user_id` context through django_rls
    and keeps writing the legacy `app.current_tenant_slug` while old policies
    are still present in existing databases.
    """

    def _set_rls_context(self, request):
        super()._set_rls_context(request)

        tenant = getattr(request, "tenant", None)
        slug = getattr(tenant, "rls_slug", None) or RLS_NO_TENANT_SLUG

        if tenant is not None and getattr(tenant, "pk", None) is not None:
            set_rls_context("tenant_id", tenant.pk, is_local=False)

        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT set_config(%s, %s, %s)",
                ["app.current_tenant_slug", str(slug), False],
            )

    def _clear_rls_context(self, request=None):
        super()._clear_rls_context(request)
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT set_config(%s, %s, %s)",
                ["app.current_tenant_slug", "", False],
            )
