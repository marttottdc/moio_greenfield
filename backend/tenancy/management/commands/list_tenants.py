"""List all tenants."""
from __future__ import annotations

from django.core.management.base import BaseCommand

from tenancy.models import Tenant


class Command(BaseCommand):
    help = "List all tenants."

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "--schema",
            action="store_true",
            help="Show schema_name column",
        )

    def handle(self, *args, **options) -> None:
        tenants = Tenant.objects.order_by("schema_name")
        show_schema = options.get("schema", False)

        if not tenants.exists():
            self.stdout.write("No tenants found.")
            return

        for t in tenants:
            parts = [str(t.pk), t.nombre, t.subdomain or "-"]
            if show_schema:
                parts.append(t.schema_name or "-")
            self.stdout.write(" | ".join(parts))
