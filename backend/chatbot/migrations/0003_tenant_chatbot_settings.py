# Generated manually for chatbot app TenantChatbotSettings

import django.db.models.deletion
from django.db import migrations, models


def migrate_tenant_config_to_chatbot_settings(apps, schema_editor):
    """
    Copy assistant/chatbot/agent settings from TenantConfiguration to TenantChatbotSettings.

    Runs per tenant schema (chatbot is TENANT_APPS). Uses public schema to read
    TenantConfiguration, then creates TenantChatbotSettings in the current tenant schema.
    """
    from django.db import connection
    from django_tenants.utils import get_public_schema_name, schema_context

    Tenant = apps.get_model("tenancy", "Tenant")
    TenantConfiguration = apps.get_model("central_hub", "TenantConfiguration")
    TenantChatbotSettings = apps.get_model("chatbot", "TenantChatbotSettings")

    schema_name = connection.schema_name
    if schema_name == get_public_schema_name():
        return  # TENANT_APPS migrations don't run on public, but guard anyway

    with schema_context(get_public_schema_name()):
        try:
            tenant = Tenant.objects.get(schema_name=schema_name)
        except Tenant.DoesNotExist:
            return
        try:
            tc = TenantConfiguration.objects.get(tenant=tenant)
        except TenantConfiguration.DoesNotExist:
            tc = None

    # Write to TenantChatbotSettings in current (tenant) schema
    defaults = {}
    if tc:
        defaults = {
            "assistants_enabled": tc.assistants_enabled,
            "assistants_default_id": tc.assistants_default_id or "",
            "conversation_handler": tc.conversation_handler or "assistant",
            "assistant_smart_reply_enabled": tc.assistant_smart_reply_enabled,
            "assistant_output_formatting_instructions": tc.assistant_output_formatting_instructions or "",
            "assistant_output_schema": tc.assistant_output_schema or "",
            "assistants_inactivity_limit": tc.assistants_inactivity_limit or 30,
            "chatbot_enabled": tc.chatbot_enabled,
            "default_agent_id": tc.default_agent_id or "",
            "agent_allow_reopen_session": tc.agent_allow_reopen_session,
            "agent_reopen_threshold": tc.agent_reopen_threshold or 360,
        }

    TenantChatbotSettings.objects.update_or_create(tenant=tenant, defaults=defaults)


def reverse_migrate(apps, schema_editor):
    """No-op on reverse - data stays in TenantChatbotSettings."""
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("central_hub", "0003_add_organization_locale"),
        ("chatbot", "0002_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="TenantChatbotSettings",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("assistants_enabled", models.BooleanField(default=False)),
                ("assistants_default_id", models.CharField(blank=True, default="", max_length=200, null=True)),
                (
                    "conversation_handler",
                    models.CharField(
                        choices=[
                            ("chatbot", "Chatbot"),
                            ("assistant", "Assistant"),
                            ("agent", "Agent"),
                        ],
                        default="assistant",
                        max_length=40,
                    ),
                ),
                ("assistant_smart_reply_enabled", models.BooleanField(default=False)),
                (
                    "assistant_output_formatting_instructions",
                    models.TextField(blank=True, default="", null=True),
                ),
                ("assistant_output_schema", models.TextField(blank=True, default="", null=True)),
                ("assistants_inactivity_limit", models.IntegerField(default=30)),
                ("chatbot_enabled", models.BooleanField(default=False)),
                ("default_agent_id", models.URLField(blank=True, default="", null=True)),
                ("agent_allow_reopen_session", models.BooleanField(default=False)),
                ("agent_reopen_threshold", models.IntegerField(default=360)),
                (
                    "tenant",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="chatbot_settings",
                        to="tenancy.tenant",
                    ),
                ),
            ],
            options={
                "db_table": "chatbot_tenant_chatbot_settings",
                "verbose_name": "Tenant Chatbot Settings",
                "verbose_name_plural": "Tenant Chatbot Settings",
            },
        ),
        migrations.RunPython(migrate_tenant_config_to_chatbot_settings, reverse_migrate),
    ]
