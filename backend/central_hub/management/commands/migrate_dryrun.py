import uuid
import time
import logging

from django.conf import settings
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError
from django.db import connection, connections
from django.db.utils import ConnectionHandler


logger = logging.getLogger("migrate_dryrun")


class Command(BaseCommand):
    help = "Run Django migrations inside a temporary SCHEMA (safe for production Postgres without superuser)."

    def handle(self, *args, **options):
        start = time.time()

        self.stdout.write(self.style.WARNING("Starting schema-based dry-run migration..."))
        logger.info("Starting schema-based dry-run migration...")

        default_conf = settings.DATABASES["default"]

        # Generate temporary SCHEMA name
        tmp_schema = f"dryrun_{uuid.uuid4().hex[:8]}"
        logger.info(f"Using temporary schema: {tmp_schema}")
        self.stdout.write(self.style.WARNING(f"Temporary schema: {tmp_schema}"))

        # Create temporary schema
        with connection.cursor() as cursor:
            try:
                cursor.execute(f'CREATE SCHEMA "{tmp_schema}"')
                logger.info(f"Created schema {tmp_schema}")
                self.stdout.write(self.style.SQL_FIELD(f"Created schema {tmp_schema}"))
            except Exception as e:
                logger.error(f"Failed to create schema: {e}")
                raise CommandError(f"Failed to create schema: {e}")

        # Override DB settings to force Django to use the new SCHEMA
        new_settings = settings.DATABASES.copy()
        new_settings["default"] = default_conf.copy()

        # Add the search_path trick
        new_settings["default"]["OPTIONS"] = new_settings["default"].get("OPTIONS", {})
        new_settings["default"]["OPTIONS"]["options"] = f"-c search_path={tmp_schema}"

        logger.info(f"Overriding Django connection to use schema {tmp_schema}")
        connections._connections = ConnectionHandler(new_settings)

        # Run migrations inside the temporary SCHEMA
        self.stdout.write(self.style.WARNING("Running migrations inside temporary schema..."))
        logger.info("Running migrations inside temporary schema...")

        try:
            call_command("migrate", interactive=False, verbosity=1)
            self.stdout.write(self.style.SUCCESS("Dry-run migration SUCCESSFUL"))
            logger.info("Dry-run migration SUCCESSFUL")
        except Exception as e:
            logger.error("Dry-run migration FAILED", exc_info=True)
            self.stdout.write(self.style.ERROR("\nDry-run migration FAILED"))
            self.stdout.write(self.style.ERROR(str(e)))
            raise
        finally:
            # Cleanup: drop the schema and everything inside
            self.stdout.write(self.style.WARNING(f"Dropping schema {tmp_schema}"))
            logger.info(f"Dropping schema {tmp_schema}")

            with connection.cursor() as cursor:
                try:
                    cursor.execute(f'DROP SCHEMA "{tmp_schema}" CASCADE')
                    logger.info(f"Dropped schema {tmp_schema}")
                except Exception as drop_e:
                    logger.error(f"Could not drop temporary schema: {drop_e}")
                    self.stdout.write(self.style.ERROR(f"Could not drop schema: {drop_e}"))

        total = time.time() - start
        self.stdout.write(self.style.SUCCESS(f"Done in {total:.2f} seconds"))
        logger.info(f"Dry-run complete in {total:.2f}s")
