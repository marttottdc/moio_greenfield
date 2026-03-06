# chatbot/management/commands/sync_tenant_tools.py
from django.core.management.base import BaseCommand
from chatbot.services.sync_tools import sync_tenant_tools


class Command(BaseCommand):
    help = "Sync agent tools into TenantToolConfiguration"

    def add_arguments(self, parser):
        parser.add_argument(
            "--resync",
            action="store_true",
            help="Force overwrite tenant customizations",
        )

        parser.add_argument(
            "--tool",
            action="append",
            dest="tools",
            help="Limit sync to a specific tool name (can be used multiple times)",
        )

        parser.add_argument(
            "--tenant",
            action="append",
            type=int,
            dest="tenants",
            help="Limit sync to a specific tenant ID (can be used multiple times)",
        )

    def handle(self, *args, **options):
        sync_tenant_tools(
            resync=options["resync"],
            tool_names=options["tools"],
            tenant_ids=options["tenants"],
        )

        self.stdout.write(self.style.SUCCESS("Tenant tools synced"))
