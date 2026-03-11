from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("central_hub", "0004_remove_tenantconfiguration"),
    ]

    operations = [
        migrations.AddField(
            model_name="platformconfiguration",
            name="shopify_client_id",
            field=models.CharField(blank=True, default="", max_length=200, null=True),
        ),
        migrations.AddField(
            model_name="platformconfiguration",
            name="shopify_client_secret",
            field=models.CharField(blank=True, default="", max_length=200, null=True),
        ),
    ]
