"""Agent Console automation definitions (recurring, event, webhook, flow-triggered runs)."""
from __future__ import annotations

from django.db import models


class AgentConsoleAutomation(models.Model):
    """Defines an automated agent run (message/prompt) and how it is triggered."""

    class TriggerType(models.TextChoices):
        MANUAL = "manual", "Manual"
        RECURRING = "recurring", "Recurring (schedule)"
        EVENT = "event", "Event"
        WEBHOOK = "webhook", "Webhook"
        FLOW = "flow", "Flow"

    workspace_slug = models.SlugField(max_length=64, default="main")
    name = models.CharField(max_length=255)
    message = models.TextField(help_text="Prompt or message sent to the agent")
    trigger_type = models.CharField(
        max_length=32,
        choices=TriggerType.choices,
        default=TriggerType.MANUAL,
    )
    trigger_config = models.JSONField(
        default=dict,
        blank=True,
        help_text="Config for trigger: cron expression, event type, webhook path, flow_id, etc.",
    )
    session_key = models.CharField(
        max_length=128,
        default="automation",
        blank=True,
        help_text="Session key for the run (e.g. 'automation', 'daily-report')",
    )
    active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "agent_console_automation"
        verbose_name = "Agent Console Automation"
        verbose_name_plural = "Agent Console Automations"

    def __str__(self) -> str:
        return self.name or str(self.id)
