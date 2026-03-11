"""Create or reset demo user for demo tenant (demo@moio.ai / demo123)."""
from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group

from tenancy.models import Tenant

User = get_user_model()
DEMO_EMAIL = "demo@moio.ai"
DEMO_PASSWORD = "demo123"


class Command(BaseCommand):
    help = "Create or reset demo user (demo@moio.ai / demo123) as tenant_admin for demo tenant"

    def add_arguments(self, parser):
        parser.add_argument(
            "--schema",
            default="demo",
            help="Tenant schema (default: demo)",
        )

    def handle(self, *args, **options):
        schema = options.get("schema", "demo").strip().lower()
        tenant = Tenant.objects.filter(schema_name=schema).first()
        if not tenant:
            self.stderr.write(
                f"Tenant schema '{schema}' not found. Run: python manage.py bootstrap_tenant --schema={schema} --name=Demo"
            )
            return 1

        user, created = User.objects.get_or_create(
            email=DEMO_EMAIL,
            defaults={
                "username": DEMO_EMAIL,
                "tenant": tenant,
                "is_staff": True,
                "is_active": True,
            },
        )
        if not created:
            user.tenant = tenant
            user.is_active = True
            user.save()

        user.set_password(DEMO_PASSWORD)
        user.save()

        group, _ = Group.objects.get_or_create(name="tenant_admin")
        if group not in user.groups.all():
            user.groups.add(group)
            self.stdout.write("Added to tenant_admin group")

        self.stdout.write(
            self.style.SUCCESS(
                f"Login: {DEMO_EMAIL} / {DEMO_PASSWORD} (tenant_admin of {tenant.nombre})"
            )
        )
        return 0
