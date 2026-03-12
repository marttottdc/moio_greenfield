"""Agent profile for Agent Console (model, vendor, thinking, verbosity)."""
from __future__ import annotations

from django.db import models

from agent_console.models.workspace import AgentConsoleWorkspace


class AgentConsoleProfile(models.Model):
    """Agent profile (model/vendor/thinking/verbosity) for a workspace or tenant-default."""

    workspace = models.ForeignKey(
        AgentConsoleWorkspace,
        on_delete=models.CASCADE,
        related_name="profiles",
        null=True,
        blank=True,
        help_text="Null = tenant-default profile",
    )
    key = models.SlugField(max_length=64, help_text="Profile key (e.g. default, support)")
    name = models.CharField(max_length=255, default="", blank=True)
    default_model = models.CharField(max_length=128, default="", blank=True)
    default_vendor = models.CharField(max_length=64, default="", blank=True)
    default_thinking = models.CharField(max_length=32, default="", blank=True)
    default_verbosity = models.CharField(max_length=32, default="", blank=True)
    system_prompt_override = models.TextField(default="", blank=True)
    tool_allowlist = models.JSONField(default=list, blank=True, help_text="List of tool IDs allowed for this profile")
    sort_order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        db_table = "agent_console_profile"
        unique_together = [("workspace", "key")]
        verbose_name = "Agent Console Profile"
        verbose_name_plural = "Agent Console Profiles"

    def __str__(self) -> str:
        return self.name or self.key
