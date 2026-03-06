import re

import django.db.models.deletion
import django_tenants.postgresql_backend.base
from django.db import migrations, models
from django.utils.text import slugify



def _build_schema_name(nombre, subdomain, tenant_code, fallback):
    seed = str(subdomain or nombre or tenant_code or fallback or "tenant").strip().lower()
    normalized = slugify(seed).replace("-", "_")
    normalized = re.sub(r"[^a-z0-9_]", "_", normalized)
    normalized = re.sub(r"_+", "_", normalized).strip("_")
    if not normalized:
        normalized = f"tenant_{fallback}"
    if normalized[0].isdigit():
        normalized = f"t_{normalized}"
    return normalized[:63]



def backfill_tenant_schema_and_domain(apps, schema_editor):
    Tenant = apps.get_model("portal", "Tenant")
    TenantDomain = apps.get_model("portal", "TenantDomain")

    taken = set(
        value
        for value in Tenant.objects.exclude(schema_name__isnull=True)
        .exclude(schema_name="")
        .values_list("schema_name", flat=True)
    )

    for tenant in Tenant.objects.order_by("id"):
        candidate = _build_schema_name(
            getattr(tenant, "nombre", None),
            getattr(tenant, "subdomain", None),
            getattr(tenant, "tenant_code", None),
            tenant.pk,
        )
        suffix = 1
        while candidate in taken:
            suffix_text = f"_{suffix}"
            candidate = f"{candidate[:63 - len(suffix_text)]}{suffix_text}"
            suffix += 1

        Tenant.objects.filter(pk=tenant.pk).update(schema_name=candidate)
        taken.add(candidate)

        host = str(getattr(tenant, "domain", "") or "").strip()
        subdomain = str(getattr(tenant, "subdomain", "") or "").strip()
        primary_domain = f"{subdomain}.{host}" if host and subdomain else host
        if primary_domain:
            TenantDomain.objects.update_or_create(
                tenant_id=tenant.pk,
                domain=primary_domain,
                defaults={"is_primary": True},
            )


class Migration(migrations.Migration):

    dependencies = [
        ("portal", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="tenant",
            name="schema_name",
            field=models.CharField(
                blank=True,
                db_index=True,
                max_length=63,
                null=True,
                unique=True,
                validators=[django_tenants.postgresql_backend.base._check_schema_name],
            ),
        ),
        migrations.CreateModel(
            name="TenantDomain",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("domain", models.CharField(db_index=True, max_length=253, unique=True)),
                ("is_primary", models.BooleanField(db_index=True, default=True)),
                (
                    "tenant",
                    models.ForeignKey(
                        db_index=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="domains",
                        to="portal.tenant",
                    ),
                ),
            ],
            options={
                "db_table": "portal_tenant_domain",
                "verbose_name": "Tenant domain",
                "verbose_name_plural": "Tenant domains",
            },
        ),
        migrations.RunPython(backfill_tenant_schema_and_domain, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="tenant",
            name="schema_name",
            field=models.CharField(
                db_index=True,
                max_length=63,
                unique=True,
                validators=[django_tenants.postgresql_backend.base._check_schema_name],
            ),
        ),
    ]
