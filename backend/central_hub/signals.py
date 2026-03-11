from contextlib import nullcontext

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models import Q
from django.db.models.signals import post_save
from django.dispatch import receiver

try:
    from django_tenants.utils import schema_context
except Exception:  # pragma: no cover - package/config may be unavailable in tests
    schema_context = None

from crm.models import Contact, ContactType
from tenancy.models import Tenant


def _tenant_schema_context(tenant):
    if (
        tenant is not None
        and getattr(settings, "DJANGO_TENANTS_ENABLED", False)
        and schema_context is not None
        and getattr(tenant, "schema_name", "")
    ):
        return schema_context(tenant.schema_name)
    return nullcontext()


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


