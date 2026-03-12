# Generated migration for Agent Console workspace, profile, plugin models.

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name="AgentConsoleWorkspace",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("slug", models.SlugField(help_text="Workspace identifier", max_length=64, unique=True)),
                ("name", models.CharField(blank=True, default="", max_length=255)),
                ("default_agent_profile_key", models.CharField(blank=True, default="", max_length=64)),
                ("specialty_prompt", models.TextField(blank=True, default="", help_text="Workspace specialization for system prompt")),
                ("default_model", models.CharField(blank=True, default="", max_length=128)),
                ("default_vendor", models.CharField(blank=True, default="", max_length=64)),
                ("default_thinking", models.CharField(blank=True, default="", max_length=32)),
                ("default_verbosity", models.CharField(blank=True, default="", max_length=32)),
                ("settings", models.JSONField(blank=True, default=dict)),
            ],
            options={
                "db_table": "agent_console_workspace",
                "verbose_name": "Agent Console Workspace",
                "verbose_name_plural": "Agent Console Workspaces",
            },
        ),
        migrations.CreateModel(
            name="AgentConsoleProfile",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("key", models.SlugField(help_text="Profile key (e.g. default, support)", max_length=64)),
                ("name", models.CharField(blank=True, default="", max_length=255)),
                ("default_model", models.CharField(blank=True, default="", max_length=128)),
                ("default_vendor", models.CharField(blank=True, default="", max_length=64)),
                ("default_thinking", models.CharField(blank=True, default="", max_length=32)),
                ("default_verbosity", models.CharField(blank=True, default="", max_length=32)),
                ("system_prompt_override", models.TextField(blank=True, default="")),
                ("tool_allowlist", models.JSONField(blank=True, default=list, help_text="List of tool IDs allowed for this profile")),
                ("sort_order", models.PositiveSmallIntegerField(default=0)),
                ("workspace", models.ForeignKey(blank=True, help_text="Null = tenant-default profile", null=True, on_delete=django.db.models.deletion.CASCADE, related_name="profiles", to="agent_console.agentconsoleworkspace")),
            ],
            options={
                "db_table": "agent_console_profile",
                "verbose_name": "Agent Console Profile",
                "verbose_name_plural": "Agent Console Profiles",
                "unique_together": {("workspace", "key")},
            },
        ),
        migrations.CreateModel(
            name="AgentConsoleWorkspaceSkill",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("skill_id", models.CharField(db_index=True, max_length=128)),
                ("name", models.CharField(blank=True, default="", max_length=255)),
                ("description", models.TextField(blank=True, default="")),
                ("body_markdown", models.TextField(blank=True, default="")),
                ("enabled", models.BooleanField(default=True)),
                ("workspace", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="workspace_skills", to="agent_console.agentconsoleworkspace")),
            ],
            options={
                "db_table": "agent_console_workspace_skill",
                "verbose_name": "Agent Console Workspace Skill",
                "verbose_name_plural": "Agent Console Workspace Skills",
                "unique_together": {("workspace", "skill_id")},
            },
        ),
        migrations.CreateModel(
            name="AgentConsolePluginAssignment",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("plugin_id", models.CharField(db_index=True, max_length=128)),
                ("user_allowlist", models.JSONField(blank=True, default=list, help_text="List of emails or 'admin' / 'member' for role-based allowlist")),
                ("workspace", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="plugin_assignments", to="agent_console.agentconsoleworkspace")),
            ],
            options={
                "db_table": "agent_console_plugin_assignment",
                "verbose_name": "Agent Console Plugin Assignment",
                "verbose_name_plural": "Agent Console Plugin Assignments",
                "unique_together": {("workspace", "plugin_id")},
            },
        ),
    ]
