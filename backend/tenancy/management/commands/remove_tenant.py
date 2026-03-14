"""
Remove a tenant and its data (single public schema + RLS).
Usage:
  python manage.py remove_tenant -s demo
  python manage.py remove_tenant -s demo --noinput

With single-schema RLS there are no tenant schemas to drop; we delete tenant-scoped
rows in public (via CASCADE or explicit deletes) and the tenant record.
"""
from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError
from django.db import connections

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

        tenant_id = tenant.id
        from django.contrib.auth import get_user_model
        UserModel = get_user_model()
        user_ids = list(UserModel.objects.filter(tenant_id=tenant_id).values_list("id", flat=True))

        conn = connections["default"]
        with conn.cursor() as cursor:
            if user_ids:
                placeholders = ",".join(["%s"] * len(user_ids))
                try:
                    cursor.execute(f"DELETE FROM authtoken_token WHERE user_id IN ({placeholders})", user_ids)
                except Exception as e:
                    self.stderr.write(self.style.WARNING(f"  Skip authtoken_token: {e}"))
                try:
                    cursor.execute(
                        f"DELETE FROM token_blacklist_blacklistedtoken WHERE token_id IN (SELECT id FROM token_blacklist_outstandingtoken WHERE user_id IN ({placeholders}))",
                        user_ids,
                    )
                except Exception as e:
                    self.stderr.write(self.style.WARNING(f"  Skip token_blacklist_blacklistedtoken: {e}"))
                try:
                    cursor.execute(f"DELETE FROM token_blacklist_outstandingtoken WHERE user_id IN ({placeholders})", user_ids)
                except Exception as e:
                    self.stderr.write(self.style.WARNING(f"  Skip token_blacklist_outstandingtoken: {e}"))
                for table, col in [
                    ("tenancy_moiouser_groups", "moiouser_id"),
                    ("tenancy_user_profile", "user_id"),
                    ("tenancy_auth_session", "user_id"),
                    ("tenancy_userapikey", "user_id"),
                ]:
                    try:
                        cursor.execute(f"DELETE FROM {table} WHERE {col} IN ({placeholders})", user_ids)
                    except Exception as e:
                        self.stderr.write(self.style.WARNING(f"  Skip {table}: {e}"))
            cursor.execute("DELETE FROM tenancy_userapikey WHERE tenant_id = %s", [tenant_id])
            cursor.execute("DELETE FROM tenancy_moiouser WHERE tenant_id = %s", [tenant_id])
            cursor.execute("DELETE FROM portal_tenant_domain WHERE tenant_id = %s", [tenant_id])
            cursor.execute("""
                SELECT tc.table_name, kcu.column_name
                FROM information_schema.table_constraints tc
                JOIN information_schema.key_column_usage kcu ON tc.constraint_name = kcu.constraint_name
                JOIN information_schema.constraint_column_usage ccu ON tc.constraint_name = ccu.constraint_name
                WHERE tc.constraint_type = 'FOREIGN KEY'
                  AND tc.table_schema = 'public'
                  AND ccu.table_name = 'portal_tenant'
            """)
            for row in cursor.fetchall():
                table_name, col_name = row[0], row[1]
                if table_name != "portal_tenant_domain":
                    try:
                        cursor.execute(f'DELETE FROM "{table_name}" WHERE "{col_name}" = %s', [tenant_id])
                    except Exception as e:
                        self.stderr.write(self.style.WARNING(f"  Skip {table_name}: {e}"))
            cursor.execute("DELETE FROM portal_tenant WHERE id = %s", [tenant_id])

        self.stdout.write(self.style.SUCCESS(f"Tenant '{schema_name}' removed."))
