from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("central_hub", "0006_shopifyoauthstate"),
    ]

    operations = [
        migrations.CreateModel(
            name="PlatformNotificationSettings",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("title", models.CharField(blank=True, default="Moio", max_length=200)),
                ("icon_url", models.URLField(blank=True, default="", max_length=500)),
                ("badge_url", models.URLField(blank=True, default="", max_length=500)),
                ("require_interaction", models.BooleanField(default=False)),
                ("renotify", models.BooleanField(default=False)),
                ("silent", models.BooleanField(default=False)),
                ("test_title", models.CharField(blank=True, default="Moio test notification", max_length=200)),
                ("test_body", models.TextField(blank=True, default="Notifications are configured for this browser.")),
            ],
            options={
                "db_table": "platform_notification_settings",
                "verbose_name": "Platform notification settings",
                "verbose_name_plural": "Platform notification settings",
            },
        ),
    ]
