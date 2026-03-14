"""
Remove a tenant and its data (single public schema + RLS).
Usage:
  python manage.py remove_tenant -s demo
  python manage.py remove_tenant -s demo --noinput

Uses Django ORM: tenant.delete() cascades to all related objects (users, contacts,
activities, etc.) according to each model's on_delete (CASCADE, SET_NULL).
"""
from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError

from tenancy.models import Tenant


class Command(BaseCommand):
    help = "Remove a tenant and its data (single public schema)."

    def add_arguments(self, parser):
        parser.add_argument(
            "-s",
            "--schema",
            dest="schema_name",
            required=True,
            help="Schema name (subdomain) of the tenant to remove (e.g. demo)",
        )
        parser.add_argument(
            "--noinput",
            "--no-input",
            action="store_true",
            help="Do not prompt for confirmation.",
        )

    def handle(self, *args, **options):
        schema_name = (options.get("schema_name") or "").strip()
        if not schema_name:
            raise CommandError("--schema is required")

        try:
            tenant = Tenant.objects.get(schema_name=schema_name)
        except Tenant.DoesNotExist:
            raise CommandError(f"Tenant with schema '{schema_name}' not found.")

        if not options.get("noinput"):
            self.stdout.write(self.style.WARNING(f"About to delete tenant '{schema_name}' (irreversible)."))
            confirm = input("Type 'yes' to confirm: ").strip().lower()
            if confirm != "yes":
                raise CommandError("Aborted.")

        tenant.delete()
        self.stdout.write(self.style.SUCCESS(f"Tenant '{schema_name}' removed."))
