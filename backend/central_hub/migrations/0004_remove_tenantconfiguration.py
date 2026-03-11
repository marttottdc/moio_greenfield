# Remove TenantConfiguration model - config now from IntegrationConfig + Tenant + TenantChatbotSettings

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("central_hub", "0003_add_organization_locale"),
        ("chatbot", "0003_tenant_chatbot_settings"),  # Data migrated in chatbot 0003
    ]

    operations = [
        migrations.DeleteModel(name="TenantConfiguration"),
    ]
