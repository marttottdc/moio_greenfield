"""Agent Console conversation sessions (tenant-scoped, JSON blob + metadata)."""
from __future__ import annotations

from django.db import models


class AgentConsoleSession(models.Model):
    """
    One conversation session for the Agent Console. Scoped by workspace within the tenant.
    Payload holds the full JSON blob (messages, summary, usage, queuedTurns); metadata
    is duplicated for listing and visibility.
    """
    workspace_slug = models.CharField(max_length=80, db_index=True)
    session_key = models.CharField(max_length=255, db_index=True)
    title = models.CharField(max_length=500, blank=True, default="")
    scope = models.CharField(max_length=20, default="shared")  # shared | private
    owner = models.JSONField(default=dict, blank=True)  # { id, email, displayName } for visibility
    payload = models.JSONField(default=dict, blank=True)  # messages, summary, summaryUpTo, usage, queuedTurns
    updated_at = models.DateTimeField(auto_now=True, db_index=True)

    class Meta:
        app_label = "agent_console"
        db_table = "agent_console_session"
        constraints = [
            models.UniqueConstraint(
                fields=["workspace_slug", "session_key"],
                name="agent_console_session_workspace_key_uniq",
            ),
        ]
        ordering = ["-updated_at"]

    def __str__(self) -> str:
        return f"{self.workspace_slug}/{self.session_key}"
