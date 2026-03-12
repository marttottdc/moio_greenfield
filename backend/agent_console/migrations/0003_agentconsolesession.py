# Agent Console sessions in DB (JSON blob + metadata)

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("agent_console", "0002_agent_console_automation"),
    ]

    operations = [
        migrations.CreateModel(
            name="AgentConsoleSession",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("workspace_slug", models.CharField(db_index=True, max_length=80)),
                ("session_key", models.CharField(db_index=True, max_length=255)),
                ("title", models.CharField(blank=True, default="", max_length=500)),
                ("scope", models.CharField(default="shared", max_length=20)),
                ("owner", models.JSONField(blank=True, default=dict)),
                ("payload", models.JSONField(blank=True, default=dict)),
                ("updated_at", models.DateTimeField(auto_now=True, db_index=True)),
            ],
            options={
                "db_table": "agent_console_session",
                "ordering": ["-updated_at"],
            },
        ),
        migrations.AddConstraint(
            model_name="agentconsolesession",
            constraint=models.UniqueConstraint(
                fields=("workspace_slug", "session_key"),
                name="agent_console_session_workspace_key_uniq",
            ),
        ),
    ]
