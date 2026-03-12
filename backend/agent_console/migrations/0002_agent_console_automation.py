# Generated migration for AgentConsoleAutomation

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("agent_console", "0001_agent_console_workspace_profile_plugin"),
    ]

    operations = [
        migrations.CreateModel(
            name="AgentConsoleAutomation",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("workspace_slug", models.SlugField(default="main", max_length=64)),
                ("name", models.CharField(max_length=255)),
                ("message", models.TextField(help_text="Prompt or message sent to the agent")),
                ("trigger_type", models.CharField(choices=[("manual", "Manual"), ("recurring", "Recurring (schedule)"), ("event", "Event"), ("webhook", "Webhook"), ("flow", "Flow")], default="manual", max_length=32)),
                ("trigger_config", models.JSONField(blank=True, default=dict, help_text="Config for trigger: cron expression, event type, webhook path, flow_id, etc.")),
                ("session_key", models.CharField(blank=True, default="automation", help_text="Session key for the run (e.g. 'automation', 'daily-report')", max_length=128)),
                ("active", models.BooleanField(default=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "db_table": "agent_console_automation",
                "verbose_name": "Agent Console Automation",
                "verbose_name_plural": "Agent Console Automations",
            },
        ),
    ]
