from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("tenancy", "0006_rls_platform_is_subdomain_platform"),
    ]

    operations = [
        migrations.AlterField(
            model_name="tenant",
            name="plan",
            field=models.CharField(blank=True, default="", max_length=40),
        ),
    ]
