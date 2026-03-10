"""
Create or reset a dev user for local login testing.
Usage: python manage.py ensure_dev_user
"""
from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from portal.models import Tenant

User = get_user_model()
DEV_EMAIL = "dev@moio.ai"
DEV_PASSWORD = "dev123"


class Command(BaseCommand):
    help = "Create or reset dev user (dev@moio.ai / dev123) for local testing"

    def handle(self, *args, **options):
        tenant = Tenant.objects.first()
        if not tenant:
            tenant = Tenant.objects.create(
                nombre="Dev Tenant",
                domain="dev.local",
                subdomain="dev",
            )
            self.stdout.write(f"Created tenant: {tenant.nombre}")

        user, created = User.objects.get_or_create(
            email=DEV_EMAIL,
            defaults={
                "username": DEV_EMAIL,
                "tenant": tenant,
                "is_staff": True,
                "is_superuser": True,
            },
        )
        if not created:
            user.tenant = tenant
            user.is_active = True
            user.save()

        user.set_password(DEV_PASSWORD)
        user.save()

        self.stdout.write(self.style.SUCCESS(
            f"Login: {DEV_EMAIL} / {DEV_PASSWORD}"
        ))
