# Integrations Hub Contract: add canonical binding status to IntegrationConfig

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("central_hub", "0008_platform_notification_settings"),
    ]

    operations = [
        migrations.AddField(
            model_name="integrationconfig",
            name="status",
            field=models.CharField(
                choices=[
                    ("connected", "Connected"),
                    ("invalid_credentials", "Invalid credentials"),
                    ("uninstalled", "Uninstalled"),
                    ("pending_link", "Pending link"),
                    ("disabled", "Disabled"),
                    ("syncing", "Syncing"),
                ],
                db_index=True,
                default="connected",
                help_text="Canonical binding status (Hub contract)",
                max_length=32,
            ),
            preserve_default=True,
        ),
    ]
