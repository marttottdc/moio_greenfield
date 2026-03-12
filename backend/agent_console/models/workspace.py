"""Workspace and workspace-level skills for Agent Console."""
from __future__ import annotations

from django.db import models


class AgentConsoleWorkspace(models.Model):
    """Per-tenant workspace (e.g. main, crm-agent)."""

    slug = models.SlugField(max_length=64, unique=True, help_text="Workspace identifier")
    name = models.CharField(max_length=255, default="", blank=True)
    default_agent_profile_key = models.CharField(max_length=64, default="", blank=True)
    specialty_prompt = models.TextField(default="", blank=True, help_text="Workspace specialization for system prompt")
    default_model = models.CharField(max_length=128, default="", blank=True)
    default_vendor = models.CharField(max_length=64, default="", blank=True)
    default_thinking = models.CharField(max_length=32, default="", blank=True)
    default_verbosity = models.CharField(max_length=32, default="", blank=True)
    settings = models.JSONField(default=dict, blank=True)

    class Meta:
        db_table = "agent_console_workspace"
        verbose_name = "Agent Console Workspace"
        verbose_name_plural = "Agent Console Workspaces"

    def __str__(self) -> str:
        return self.name or self.slug


class AgentConsoleWorkspaceSkill(models.Model):
    """Skill enabled for a workspace (injected into runtime)."""

    workspace = models.ForeignKey(
        AgentConsoleWorkspace,
        on_delete=models.CASCADE,
        related_name="workspace_skills",
    )
    skill_id = models.CharField(max_length=128, db_index=True)
    name = models.CharField(max_length=255, default="", blank=True)
    description = models.TextField(default="", blank=True)
    body_markdown = models.TextField(default="", blank=True)
    enabled = models.BooleanField(default=True)

    class Meta:
        db_table = "agent_console_workspace_skill"
        unique_together = [("workspace", "skill_id")]
        verbose_name = "Agent Console Workspace Skill"
        verbose_name_plural = "Agent Console Workspace Skills"
