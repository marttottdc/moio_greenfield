from django.db import migrations, models
import django.db.models.deletion
import uuid


def default_provisioning_stages():
    return {
        "tenant_creation": {"status": "pending", "started_at": None, "finished_at": None, "error": ""},
        "tenant_seeding": {"status": "pending", "started_at": None, "finished_at": None, "error": ""},
        "primary_user_creation": {"status": "pending", "started_at": None, "finished_at": None, "error": ""},
    }


class Migration(migrations.Migration):

    dependencies = [
        ("tenancy", "0006_rls_platform_is_subdomain_platform"),
        ("central_hub", "0003_plan_policy_fields"),
    ]

    operations = [
        migrations.CreateModel(
            name="ProvisioningJob",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("status", models.CharField(choices=[("pending", "Pending"), ("running", "Running"), ("success", "Success"), ("failure", "Failure")], default="pending", max_length=20)),
                ("current_stage", models.CharField(blank=True, choices=[("tenant_creation", "Tenant creation"), ("tenant_seeding", "Tenant seeding"), ("primary_user_creation", "Primary user creation")], default="", max_length=40)),
                ("stages", models.JSONField(blank=True, default=default_provisioning_stages)),
                ("requested_name", models.CharField(max_length=150)),
                ("requested_email", models.EmailField(max_length=254)),
                ("requested_username", models.CharField(max_length=150)),
                ("requested_subdomain", models.CharField(blank=True, default="", max_length=100)),
                ("requested_domain", models.CharField(blank=True, default="", max_length=150)),
                ("requested_locale", models.CharField(default="es", max_length=10)),
                ("error_message", models.TextField(blank=True, default="")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("tenant", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="provisioning_jobs", to="tenancy.tenant")),
                ("user", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="provisioning_jobs", to="tenancy.moiouser")),
            ],
            options={
                "verbose_name": "Provisioning job",
                "verbose_name_plural": "Provisioning jobs",
                "db_table": "platform_provisioning_job",
                "ordering": ["-created_at"],
            },
        ),
    ]
