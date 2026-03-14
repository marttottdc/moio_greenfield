"""
Temporarily disable RLS on all tenant-scoped tables.
Re-enable with: python manage.py enable_rls

  python manage.py disable_rls
"""
from django.core.management.base import BaseCommand
from django.db import connection

from .backfill_tenant_uuid import TABLES


class Command(BaseCommand):
    help = "Disable RLS on tenant-scoped tables (temporary; use enable_rls to turn back on)."

    def handle(self, *args, **options):
        q = connection.ops.quote_name
        done = 0
        with connection.cursor() as cursor:
            for table in TABLES:
                try:
                    tn = q(table)
                    cursor.execute("ALTER TABLE %s DISABLE ROW LEVEL SECURITY" % tn)
                    done += 1
                    self.stdout.write("Disabled: %s" % table)
                except Exception as e:
                    self.stderr.write("Skip %s: %s" % (table, e))
        connection.commit()
        self.stdout.write(self.style.SUCCESS("RLS disabled on %s table(s). Run enable_rls to re-enable." % done))
