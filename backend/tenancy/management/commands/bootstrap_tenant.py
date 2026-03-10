"""Create or update a tenant and optional primary domain."""
from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError

from tenancy.models import Tenant, TenantDomain
from tenancy.validators import validate_subdomain_rfc


class Command(BaseCommand):
    help = "Create or update a tenant and optional primary domain."

    def add_arguments(self, parser) -> None:
        parser.add_argument("--schema", required=True, help="Tenant schema name (e.g. acme)")
        parser.add_argument("--name", required=True, help="Tenant display name")
        parser.add_argument("--domain", default="", help="Base domain (e.g. moio.ai)")
        parser.add_argument("--subdomain", default="", help="Subdomain (e.g. acme -> acme.moio.ai)")
        parser.add_argument("--plan", default="free", choices=["free", "pro", "business"])

    def handle(self, *args, **options) -> None:
        schema_name = str(options.get("schema", "")).strip().lower()
        name = str(options.get("name", "")).strip()
        domain = str(options.get("domain", "")).strip().lower()
        subdomain = str(options.get("subdomain", "")).strip().lower()
        plan = str(options.get("plan", "free")).lower()

        if not schema_name:
            raise CommandError("--schema is required")
        if not name:
            raise CommandError("--name is required")

        effective_subdomain = subdomain or schema_name
        if effective_subdomain:
            try:
                validate_subdomain_rfc(effective_subdomain)
            except ValueError as e:
                raise CommandError(f"subdomain invalid: {e}") from e

        tenant, created = Tenant.objects.get_or_create(
            schema_name=schema_name,
            defaults={
                "nombre": name,
                "domain": domain or "localhost",
                "subdomain": subdomain or schema_name,
                "plan": plan,
            },
        )
        changed = False
        if tenant.nombre != name:
            tenant.nombre = name
            changed = True
        if tenant.domain != (domain or "localhost"):
            tenant.domain = domain or "localhost"
            changed = True
        if tenant.subdomain != (subdomain or schema_name):
            tenant.subdomain = subdomain or schema_name
            changed = True
        if changed:
            tenant.save(update_fields=["nombre", "domain", "subdomain"])

        self.stdout.write(
            self.style.SUCCESS(
                f"tenant {'created' if created else 'ready'}: schema={tenant.schema_name} name={tenant.nombre}",
            ),
        )

        primary = tenant.primary_domain
        if primary:
            domain_row, domain_created = TenantDomain.objects.get_or_create(
                domain=primary,
                defaults={"tenant": tenant, "is_primary": True},
            )
            if domain_row.tenant_id != tenant.id:
                domain_row.tenant = tenant
                domain_row.save(update_fields=["tenant"])
            self.stdout.write(
                self.style.SUCCESS(
                    f"domain {'created' if domain_created else 'ready'}: {domain_row.domain} -> {tenant.schema_name}",
                ),
            )
