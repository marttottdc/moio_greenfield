from contextlib import nullcontext

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models import Q
from django.db.models.signals import post_save
from django.dispatch import receiver

try:
    from tenancy.tenant_support import public_schema_context
except Exception:  # pragma: no cover - package/config may be unavailable in tests
    public_schema_context = None

from crm.models import Contact, ContactType, ContactTypeChoices
from tenancy.models import Tenant
from tenancy.tenant_support import tenant_rls_context


DEFAULT_CONTACT_TYPES = (
    (ContactTypeChoices.LEAD, True),
    (ContactTypeChoices.RECURRENT, False),
    (ContactTypeChoices.EXPERT, False),
    (ContactTypeChoices.CUSTOMER, False),
    (ContactTypeChoices.VIP, False),
    (ContactTypeChoices.ADMIN, False),
    (ContactTypeChoices.INTERNAL, False),
    (ContactTypeChoices.USER, False),
)


def _tenant_rls_context(tenant):
    slug = getattr(tenant, "rls_slug", None) if tenant is not None else None
    if slug:
        return tenant_rls_context(slug)
    if (
        tenant is not None
        and getattr(settings, "DJANGO_TENANTS_ENABLED", False)
        and public_schema_context is not None
        and getattr(tenant, "schema_name", "")
    ):
        return public_schema_context(tenant.schema_name)
    return nullcontext()


@receiver(post_save, sender=Tenant)
def seed_tenant_crm_defaults(sender, instance, created, **kwargs):
    """Seed CRM defaults required by user/contact flows for every new tenant."""
    if not created:
        return

    with _tenant_rls_context(instance):
        for contact_type_name, is_default in DEFAULT_CONTACT_TYPES:
            contact_type, was_created = ContactType.objects.get_or_create(
                tenant=instance,
                name=contact_type_name,
                defaults={"is_default": is_default},
            )
            if not was_created and is_default and not contact_type.is_default:
                contact_type.is_default = True
                contact_type.save(update_fields=["is_default"])


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
    
    with _tenant_rls_context(instance.tenant):
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


