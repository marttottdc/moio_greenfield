# Subdomain obligatorio. Rellenar NULL con 'platform'. Platform = tenant con subdomain 'platform' (root).

from django.db import migrations, models


def backfill_subdomain_null(apps, schema_editor):
    """Rellenar subdomain NULL con 'platform' para poder hacer NOT NULL."""
    Tenant = apps.get_model("tenancy", "Tenant")
    Tenant.objects.filter(subdomain__isnull=True).update(subdomain="platform")
    # Por si hay '' (vacío)
    Tenant.objects.filter(subdomain="").update(subdomain="platform")


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("tenancy", "0004_rls_policy_platform_visible_to_all"),
    ]

    operations = [
        migrations.RunPython(backfill_subdomain_null, noop_reverse),
        migrations.AlterField(
            model_name="tenant",
            name="subdomain",
            field=models.CharField(blank=False, db_index=True, max_length=100, null=False, unique=True),
        ),
    ]
