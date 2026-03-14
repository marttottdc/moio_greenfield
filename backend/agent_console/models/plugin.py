"""Plugin assignment and installation models for Agent Console."""
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
    is_enabled = models.BooleanField(default=True)
    plugin_config = models.JSONField(default=dict, blank=True)
    notes = models.TextField(default="", blank=True)
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


class AgentConsoleInstalledPlugin(models.Model):
    """Installed plugin bundles stored in tenant DB."""

    plugin_id = models.CharField(max_length=128, unique=True, db_index=True)
    name = models.CharField(max_length=255, blank=True, default="")
    version = models.CharField(max_length=64, blank=True, default="")
    enabled = models.BooleanField(default=True)
    is_platform_approved = models.BooleanField(default=False)
    checksum_sha256 = models.CharField(max_length=64, blank=True, default="")
    manifest = models.JSONField(default=dict, blank=True)
    bundle_zip = models.BinaryField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "agent_console_installed_plugin"
        verbose_name = "Agent Console Installed Plugin"
        verbose_name_plural = "Agent Console Installed Plugins"
