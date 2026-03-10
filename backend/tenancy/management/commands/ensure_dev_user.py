"""Create or reset a dev user for local login testing."""
from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group

from tenancy.models import Tenant

User = get_user_model()
DEV_EMAIL = "dev@moio.ai"
DEV_PASSWORD = "dev123"


class Command(BaseCommand):
    help = "Create or reset dev user (dev@moio.ai / dev123) as tenant_admin for dev tenant"

    def add_arguments(self, parser):
        parser.add_argument(
            "--schema",
            default="dev",
            help="Tenant schema (default: dev)",
        )

    def handle(self, *args, **options):
        schema = options.get("schema", "dev").strip().lower()
        tenant = Tenant.objects.filter(schema_name=schema).first()
        if not tenant:
            tenant = Tenant.objects.create(
                nombre="Dev Tenant",
                domain="localhost",
                subdomain="dev",
                schema_name=schema,
            )
            self.stdout.write(f"Created tenant: {tenant.nombre} (schema={schema})")

        user, created = User.objects.get_or_create(
            email=DEV_EMAIL,
            defaults={
                "username": DEV_EMAIL,
                "tenant": tenant,
                "is_staff": True,
                "is_active": True,
            },
        )
        if not created:
            user.tenant = tenant
            user.is_active = True
            user.save()

        user.set_password(DEV_PASSWORD)
        user.save()

        # tenant_admin role via Django Group
        group, _ = Group.objects.get_or_create(name="tenant_admin")
        if group not in user.groups.all():
            user.groups.add(group)
            self.stdout.write("Added to tenant_admin group")

        self.stdout.write(self.style.SUCCESS(
            f"Login: {DEV_EMAIL} / {DEV_PASSWORD} (tenant_admin of {tenant.nombre})"
        ))
