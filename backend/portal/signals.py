from contextlib import nullcontext

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models import Q
from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver
from django.utils import timezone

try:
    from django_tenants.utils import schema_context
except Exception:  # pragma: no cover - package/config may be unavailable in tests
    schema_context = None

from crm.models import Contact, ContactType
from portal.entitlements_defaults import get_default_entitlements_for_plan
from portal.models import (
    Tenant,
    TenantDomain,
    TenantConfiguration,
    MoioUser,
    UserProfile,
)


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
def create_tenant_configurations(sender, instance, created, **kwargs):
    if created:
        TenantConfiguration.objects.create(tenant=instance)


@receiver(post_save, sender=Tenant)
def seed_tenant_entitlements(sender, instance, created, **kwargs):
    """Seed Tenant.features/limits/ui from plan when created."""
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
    """Ensure one UserProfile per MoioUser."""
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


@receiver(post_save, sender=get_user_model())
def create_internal_contact(sender, instance, **kwargs):
    """
    Ensure there is one Contact per user (same tenant) matched by
    either e‑mail *or* phone, or already linked via linked_user.
    If it already exists we update it; otherwise we create it.
    Always sets linked_user to establish the bidirectional relationship.
    """
    if not instance.tenant:
        return
    
    with _tenant_schema_context(instance.tenant):
        ctype, _ = ContactType.objects.get_or_create(
            name="User",
            tenant=instance.tenant,
        )

        contact = (
            Contact.objects
            .filter(
                Q(linked_user=instance) | Q(email=instance.email) | Q(phone=instance.phone),
                tenant=instance.tenant,
            )
            .first()
        )

        defaults = {
            "fullname": f"{instance.first_name} {instance.last_name}",
            "email": instance.email,
            "phone": instance.phone,
            "ctype": ctype,
            "source": "user_management",
            "company": instance.tenant.nombre if instance.tenant else "",
            "linked_user": instance,
        }

        with transaction.atomic():
            if contact:
                for field, value in defaults.items():
                    setattr(contact, field, value)
                contact.save(update_fields=list(defaults.keys()))
            else:
                Contact.objects.create(tenant=instance.tenant, **defaults)


