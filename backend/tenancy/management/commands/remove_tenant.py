"""
Remove a tenant and its PostgreSQL schema.
Usage:
  python manage.py remove_tenant -s test_2
  python manage.py remove_tenant -s test_2 --noinput

Avoids django-tenants delete_tenant bug (interactive prompt) and the CASCADE
issue (deleting Tenant triggers cascade to MoioUser -> UserNotificationPreference
in tenant schema, which fails after schema is dropped).
"""
from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError
from django.db import connections

from tenancy.models import Tenant
from django_tenants.utils import get_tenant_database_alias, schema_exists


class Command(BaseCommand):
    help = "Remove a tenant and drop its PostgreSQL schema."

    def add_arguments(self, parser):
        parser.add_argument(
            "-s",
            "--schema",
            dest="schema_name",
            required=True,
            help="Schema name of the tenant to remove (e.g. test_2)",
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
        # Get user IDs for this tenant (for cascading deletes in public schema)
        from django.contrib.auth import get_user_model
        UserModel = get_user_model()
        user_ids = list(UserModel.objects.filter(tenant_id=tenant_id).values_list("id", flat=True))

        db_alias = get_tenant_database_alias()
        connection = connections[db_alias]
        with connection.cursor() as cursor:
            # 1. Drop schema first (removes all tenant-scoped data)
            if schema_exists(schema_name):
                cursor.execute(f'DROP SCHEMA "{schema_name}" CASCADE')
                self.stdout.write(f"Dropped schema {schema_name}")

            # 2. Delete public-schema rows (order: FKs first)
            if user_ids:
                placeholders = ",".join(["%s"] * len(user_ids))
                cursor.execute(
                    f"DELETE FROM authtoken_token WHERE user_id IN ({placeholders})",
                    user_ids,
                )
                cursor.execute(
                    f"DELETE FROM token_blacklist_blacklistedtoken WHERE token_id IN (SELECT id FROM token_blacklist_outstandingtoken WHERE user_id IN ({placeholders}))",
                    user_ids,
                )
                cursor.execute(
                    f"DELETE FROM token_blacklist_outstandingtoken WHERE user_id IN ({placeholders})",
                    user_ids,
                )
                cursor.execute(
                    f"DELETE FROM tenancy_moiouser_groups WHERE moiouser_id IN ({placeholders})",
                    user_ids,
                )
                cursor.execute(
                    f"DELETE FROM tenancy_user_profile WHERE user_id IN ({placeholders})",
                    user_ids,
                )
                cursor.execute(
                    f"DELETE FROM tenancy_auth_session WHERE user_id IN ({placeholders})",
                    user_ids,
                )
                cursor.execute(
                    f"DELETE FROM tenancy_userapikey WHERE user_id IN ({placeholders})",
                    user_ids,
                )
            cursor.execute(
                "DELETE FROM tenancy_userapikey WHERE tenant_id = %s",
                [tenant_id],
            )
            cursor.execute(
                "DELETE FROM tenancy_moiouser WHERE tenant_id = %s",
                [tenant_id],
            )
            cursor.execute(
                "DELETE FROM portal_tenant_domain WHERE tenant_id = %s",
                [tenant_id],
            )
            # Delete from all tables that have FK to portal_tenant (public schema only)
            cursor.execute("""
                SELECT tc.table_name, kcu.column_name
                FROM information_schema.table_constraints tc
                JOIN information_schema.key_column_usage kcu
                    ON tc.constraint_name = kcu.constraint_name
                JOIN information_schema.constraint_column_usage ccu
                    ON tc.constraint_name = ccu.constraint_name
                WHERE tc.constraint_type = 'FOREIGN KEY'
                    AND tc.table_schema = 'public'
                    AND ccu.table_name = 'portal_tenant'
            """)
            for row in cursor.fetchall():
                table_name, col_name = row[0], row[1]
                if table_name != "portal_tenant_domain":  # already deleted
                    try:
                        cursor.execute(
                            f'DELETE FROM "{table_name}" WHERE "{col_name}" = %s',
                            [tenant_id],
                        )
                    except Exception as e:
                        self.stderr.write(self.style.WARNING(f"  Skip {table_name}: {e}"))
            cursor.execute(
                "DELETE FROM portal_tenant WHERE id = %s",
                [tenant_id],
            )

        self.stdout.write(self.style.SUCCESS(f"Tenant '{schema_name}' removed."))
