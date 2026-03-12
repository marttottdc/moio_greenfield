from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('crm', '0006_rename_crm_shopify_tenant__g7h8i9_idx_shopify_cus_tenant__5e2d69_idx_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='contacttype',
            name='is_default',
            field=models.BooleanField(default=False),
        ),
    ]
