"""Tenancy signals: UserProfile creation, tenant entitlements seeding."""
from contextlib import nullcontext

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils import timezone

try:
    from tenancy.tenant_support import schema_context
except Exception:
    schema_context = None

from tenancy.entitlements_defaults import get_default_entitlements_for_plan
from tenancy.models import Tenant, TenantDomain, UserProfile


def _tenant_schema_context(tenant):
    if (
        tenant is not None
        and getattr(settings, "DJANGO_TENANTS_ENABLED", False)
        and schema_context is not None
        and getattr(tenant, "schema_name", "")
    ):
        return schema_context(tenant.schema_name)
    return nullcontext()


@receiver(post_save, sender=Tenant)
def seed_tenant_entitlements(sender, instance, created, **kwargs):
    if not created:
        return
    defaults = get_default_entitlements_for_plan(getattr(instance, "plan", "free"))
    instance.features = defaults["features"]
    instance.limits = defaults["limits"]
    instance.ui = defaults.get("ui", {})
    instance.entitlements_updated_at = timezone.now()
    Tenant.objects.filter(pk=instance.pk).update(
        features=instance.features,
        limits=instance.limits,
        ui=instance.ui,
        entitlements_updated_at=instance.entitlements_updated_at,
    )


@receiver(post_save, sender=Tenant)
def sync_primary_tenant_domain(sender, instance, **kwargs):
    primary_domain = str(getattr(instance, "primary_domain", "") or "").strip()
    if not primary_domain:
        return
    TenantDomain.objects.update_or_create(
        tenant=instance,
        domain=primary_domain,
        defaults={"is_primary": True},
    )


@receiver(post_save, sender=get_user_model())
def create_user_profile(sender, instance, created, **kwargs):
    if created:
        UserProfile.objects.get_or_create(
            user=instance,
            defaults={
                "display_name": f"{instance.first_name} {instance.last_name}".strip() or instance.username,
                "locale": "en",
                "timezone": "UTC",
                "onboarding_state": "pending",
                "default_landing": "/dashboard",
            },
        )
