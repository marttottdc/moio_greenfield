"""
Seed Capability and Role from tenancy.capabilities (CAPABILITY_KEYS and ROLE_CAPABILITIES).
Run after migrations: python manage.py seed_roles_and_capabilities
"""
from django.core.management.base import BaseCommand

from tenancy.capabilities import CAPABILITY_KEYS, ROLE_CAPABILITIES
from tenancy.rbac import ROLE_ORDER


CAPABILITY_LABELS = {
    "crm_contacts_read": "Read CRM contacts",
    "crm_contacts_write": "Write CRM contacts",
    "campaigns_read": "Read campaigns",
    "campaigns_send": "Send campaigns",
    "flows_read": "Read flows",
    "flows_run": "Run flows",
    "flows_edit": "Edit flows",
    "settings_integrations_manage": "Manage integrations",
    "users_manage": "Manage users",
}

ROLE_NAMES = {
    "viewer": "Viewer",
    "member": "Member",
    "manager": "Manager",
    "tenant_admin": "Tenant Admin",
    "platform_admin": "Platform Admin",
}


class Command(BaseCommand):
    help = "Seed platform_capability and platform_role from tenancy.capabilities."

    def handle(self, *args, **options):
        from central_hub.models import Capability, Role

        # Ensure all capability keys exist
        for key in sorted(CAPABILITY_KEYS):
            cap, created = Capability.objects.get_or_create(
                key=key,
                defaults={"label": CAPABILITY_LABELS.get(key, key.replace("_", " ").title()), "description": ""},
            )
            if created:
                self.stdout.write(f"Created capability: {key}")

        # Ensure all default roles exist with correct capabilities
        for idx, slug in enumerate(ROLE_ORDER):
            caps_set = ROLE_CAPABILITIES.get(slug, set())
            role, created = Role.objects.get_or_create(
                slug=slug,
                defaults={
                    "name": ROLE_NAMES.get(slug, slug.replace("_", " ").title()),
                    "display_order": idx,
                },
            )
            if created:
                self.stdout.write(f"Created role: {slug}")
            role.display_order = idx
            role.name = ROLE_NAMES.get(slug, role.name or slug.replace("_", " ").title())
            role.save()
            caps = list(Capability.objects.filter(key__in=caps_set))
            role.capabilities.set(caps)
        self.stdout.write(self.style.SUCCESS("Roles and capabilities seeded."))
