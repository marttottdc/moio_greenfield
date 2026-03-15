# Generated manually for PlatformAdminKpiSnapshot (platform admin KPIs cache).

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("central_hub", "0006_add_capability_and_role"),
    ]

    operations = [
        migrations.CreateModel(
            name="PlatformAdminKpiSnapshot",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("tenant_id", models.IntegerField(blank=True, db_index=True, null=True)),
                ("period_key", models.CharField(db_index=True, default="all", max_length=20)),
                ("contacts", models.PositiveIntegerField(default=0)),
                ("accounts", models.PositiveIntegerField(default=0)),
                ("deals", models.PositiveIntegerField(default=0)),
                ("activities", models.PositiveIntegerField(default=0)),
                ("flow_executions", models.PositiveIntegerField(default=0)),
                ("agent_sessions", models.PositiveIntegerField(default=0)),
                ("total_activity_per_hour", models.FloatField(blank=True, null=True)),
                ("updated_at", models.DateTimeField(auto_now=True, db_index=True)),
            ],
            options={
                "verbose_name": "Platform admin KPI snapshot",
                "verbose_name_plural": "Platform admin KPI snapshots",
                "db_table": "platform_admin_kpi_snapshot",
                "ordering": ["-updated_at"],
            },
        ),
        migrations.AddConstraint(
            model_name="platformadminkpisnapshot",
            constraint=models.UniqueConstraint(
                condition=models.Q(tenant_id__isnull=True),
                fields=("period_key",),
                name="platform_admin_kpi_snapshot_all_period_uniq",
            ),
        ),
        migrations.AddConstraint(
            model_name="platformadminkpisnapshot",
            constraint=models.UniqueConstraint(
                condition=models.Q(tenant_id__isnull=False),
                fields=("tenant_id", "period_key"),
                name="platform_admin_kpi_snapshot_tenant_period_uniq",
            ),
        ),
    ]
