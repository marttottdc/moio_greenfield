"""
Re-enable RLS (and FORCE) on all tenant-scoped tables after disable_rls.

  python manage.py enable_rls
"""
from django.core.management.base import BaseCommand
from django.db import connection

from .backfill_tenant_uuid import TABLES


class Command(BaseCommand):
    help = "Re-enable RLS on tenant-scoped tables (after disable_rls)."

    def handle(self, *args, **options):
        q = connection.ops.quote_name
        done = 0
        with connection.cursor() as cursor:
            for table in TABLES:
                try:
                    tn = q(table)
                    cursor.execute("ALTER TABLE %s ENABLE ROW LEVEL SECURITY" % tn)
                    cursor.execute("ALTER TABLE %s FORCE ROW LEVEL SECURITY" % tn)
                    done += 1
                    self.stdout.write("Enabled: %s" % table)
                except Exception as e:
                    self.stderr.write("Skip %s: %s" % (table, e))
        connection.commit()
        self.stdout.write(self.style.SUCCESS("RLS enabled on %s table(s)." % done))
