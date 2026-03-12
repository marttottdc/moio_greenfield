"""Plugin assignment (user allowlist) for Agent Console."""
from __future__ import annotations

from django.db import models

from agent_console.models.workspace import AgentConsoleWorkspace


class AgentConsolePluginAssignment(models.Model):
    """Which users (by email or role) can use a plugin in a workspace."""

    workspace = models.ForeignKey(
        AgentConsoleWorkspace,
        on_delete=models.CASCADE,
        related_name="plugin_assignments",
    )
    plugin_id = models.CharField(max_length=128, db_index=True)
    user_allowlist = models.JSONField(
        default=list,
        blank=True,
        help_text="List of emails or 'admin' / 'member' for role-based allowlist",
    )

    class Meta:
        db_table = "agent_console_plugin_assignment"
        unique_together = [("workspace", "plugin_id")]
        verbose_name = "Agent Console Plugin Assignment"
        verbose_name_plural = "Agent Console Plugin Assignments"
