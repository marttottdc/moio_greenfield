from contextlib import nullcontext

from django.conf import settings
from celery import Task
from rest_framework import viewsets
from rest_framework.exceptions import PermissionDenied

from central_hub.context_utils import current_tenant, set_current_tenant
from central_hub.models import Tenant

try:
    from django_tenants.utils import schema_context
except Exception:  # pragma: no cover - package/config may be unavailable in tests
    schema_context = None


class TenantScopedViewSet(viewsets.ModelViewSet):
    """A ViewSet base class that ensures objects belong to current tenant."""

    def get_object(self):
        obj = super().get_object()
        tenant = current_tenant.get()
        if hasattr(obj, "tenant") and obj.tenant != tenant:
            raise PermissionDenied("Object does not belong to your tenant.")
        return obj


class TenantAwareTask(Task):
    """Celery task that restores tenant context when provided."""

    def __call__(self, *args, **kwargs):
        tenant_id = kwargs.pop("tenant_id", None)
        if tenant_id:
            tenant = Tenant.objects.get(pk=tenant_id)
            set_current_tenant(tenant)
            if (
                getattr(settings, "DJANGO_TENANTS_ENABLED", False)
                and schema_context is not None
                and getattr(tenant, "schema_name", "")
            ):
                with schema_context(tenant.schema_name):
                    return super().__call__(*args, **kwargs)
        return super().__call__(*args, **kwargs)
