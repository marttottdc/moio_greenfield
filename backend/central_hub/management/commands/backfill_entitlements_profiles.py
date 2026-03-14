"""
Backfill Tenant.features/limits/ui and UserProfile for existing tenants/users.

Run after deploying the new models:
  python manage.py backfill_entitlements_profiles
"""
from __future__ import annotations

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand

from central_hub.entitlements_defaults import get_default_entitlements_for_plan
from central_hub.plan_policy import get_plan_by_key, get_self_provision_default_plan
from central_hub.models import Tenant, MoioUser, UserProfile


UserModel = get_user_model()


class Command(BaseCommand):
    help = "Backfill Tenant features/limits/ui and UserProfile for existing tenants and users."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Only report what would be created, do not write.",
        )
        parser.add_argument(
            "--full-access",
            action="store_true",
            help="Assign business-tier entitlements (all features, high limits) to existing tenants to avoid deployment conflicts.",
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        full_access = options["full_access"]
        if dry_run:
            self.stdout.write(self.style.WARNING("Dry run: no changes will be written."))
        if full_access:
            self.stdout.write(self.style.NOTICE("Full-access mode: existing tenants will get business-tier entitlements."))

        updated_tenants = 0
        for tenant in Tenant.objects.all():
            if tenant.features or tenant.limits:
                continue
            if dry_run:
                self.stdout.write(f"Would backfill Tenant features/limits for tenant id={tenant.id} ({tenant.nombre})")
                updated_tenants += 1
                continue
            if full_access:
                defaults = get_default_entitlements_for_plan(get_plan_by_key("business").key)
            else:
                plan_key = getattr(tenant, "plan", "") or get_self_provision_default_plan().key
                defaults = get_default_entitlements_for_plan(plan_key)
            tenant.features = defaults["features"]
            tenant.limits = defaults["limits"]
            tenant.ui = defaults.get("ui", {})
            tenant.save(update_fields=["features", "limits", "ui"])
            updated_tenants += 1
            self.stdout.write(f"Backfilled Tenant features/limits for tenant id={tenant.id}")


        created_profiles = 0
        for user in UserModel.objects.all():
            if UserProfile.objects.filter(user=user).exists():
                continue
            if dry_run:
                self.stdout.write(f"Would create UserProfile for user id={user.id} ({user.email})")
                created_profiles += 1
                continue
            UserProfile.objects.create(
                user=user,
                display_name=f"{user.first_name} {user.last_name}".strip() or user.username,
                locale="en",
                timezone="UTC",
                onboarding_state="pending",
                default_landing="/dashboard",
            )
            created_profiles += 1
            self.stdout.write(f"Created UserProfile for user id={user.id}")

        self.stdout.write(
            self.style.SUCCESS(
                f"Backfill complete: {updated_tenants} tenants, {created_profiles} profiles."
            )
        )
