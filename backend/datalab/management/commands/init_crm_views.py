"""
Management command to initialize default CRM Views for tenants.
"""
from django.core.management.base import BaseCommand
from portal.models import Tenant

from datalab.crm_sources.registry import CRMViewRegistry


class Command(BaseCommand):
    help = "Initialize default CRM Views for tenants"

    def add_arguments(self, parser):
        parser.add_argument(
            '--tenant-id',
            type=int,
            help='Initialize views for a specific tenant ID (if not provided, initializes for all tenants)',
        )
        parser.add_argument(
            '--force',
            action='store_true',
            help='Force re-initialization even if views already exist',
        )

    def handle(self, *args, **options):
        tenant_id = options.get('tenant_id')
        force = options.get('force', False)

        if tenant_id:
            tenants = Tenant.objects.filter(id=tenant_id)
            if not tenants.exists():
                self.stdout.write(self.style.ERROR(f"Tenant {tenant_id} not found"))
                return
        else:
            tenants = Tenant.objects.all()

        total_created = 0
        for tenant in tenants:
            self.stdout.write(f"Initializing CRM Views for tenant: {tenant.nombre} (ID: {tenant.id})")
            
            if force:
                # Delete existing views
                from datalab.crm_sources.models import CRMView
                CRMView.objects.filter(tenant=tenant).delete()
            
            created_views = CRMViewRegistry.initialize_defaults(tenant)
            total_created += len(created_views)
            
            if created_views:
                self.stdout.write(
                    self.style.SUCCESS(
                        f"  Created {len(created_views)} CRM Views: "
                        f"{', '.join(v.key for v in created_views)}"
                    )
                )
            else:
                self.stdout.write(self.style.WARNING("  No views created (already exist)"))

        self.stdout.write(
            self.style.SUCCESS(f"\nTotal CRM Views created: {total_created}")
        )
