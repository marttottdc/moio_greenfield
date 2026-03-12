from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("central_hub", "0005_platformconfiguration_shopify_oauth"),
    ]

    operations = [
        migrations.CreateModel(
            name="ShopifyOAuthState",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("state", models.CharField(db_index=True, max_length=64, unique=True)),
                ("shop_domain", models.CharField(db_index=True, max_length=255)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
            ],
            options={
                "db_table": "shopify_oauth_state",
            },
        ),
        migrations.AddIndex(
            model_name="shopifyoauthstate",
            index=models.Index(fields=["state"], name="shopify_oauth_state_idx"),
        ),
        migrations.AddIndex(
            model_name="shopifyoauthstate",
            index=models.Index(fields=["created_at"], name="shopify_oauth_created_idx"),
        ),
    ]
