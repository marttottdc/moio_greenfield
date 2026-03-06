from __future__ import annotations

import uuid

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone

from portal.models import Tenant


SESSION_KEY_PREFIXES = ("manual:", "schedule:", "event:", "campaign:")


class Robot(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="robots")

    name = models.CharField(max_length=255)
    slug = models.SlugField(max_length=255)
    description = models.TextField(blank=True, default="")

    system_prompt = models.TextField(blank=True, default="")
    bootstrap_context = models.JSONField(default=dict, blank=True)

    model_config = models.JSONField(default=dict, blank=True)
    tools_config = models.JSONField(default=dict, blank=True)
    targets = models.JSONField(default=dict, blank=True)
    operation_window = models.JSONField(default=dict, blank=True)
    schedule = models.JSONField(default=dict, blank=True)
    compaction_config = models.JSONField(default=dict, blank=True)
    rate_limits = models.JSONField(default=dict, blank=True)

    enabled = models.BooleanField(default=True)
    hard_timeout_seconds = models.PositiveIntegerField(default=3600)

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_robots",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "robots_robot"
        unique_together = [("tenant", "slug")]
        indexes = [
            models.Index(fields=["tenant", "enabled"]),
            models.Index(fields=["tenant", "slug"]),
        ]

    def __str__(self) -> str:
        return f"{self.name} ({self.slug})"


class RobotSession(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    robot = models.ForeignKey(Robot, on_delete=models.CASCADE, related_name="sessions")
    session_key = models.CharField(max_length=255, db_index=True)
    run_id = models.UUIDField(null=True, blank=True, db_index=True)

    metadata = models.JSONField(default=dict, blank=True)
    transcript = models.JSONField(default=list, blank=True)
    intent_state = models.JSONField(default=dict, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "robots_session"
        unique_together = [("robot", "session_key")]
        indexes = [
            models.Index(fields=["robot", "updated_at"]),
            models.Index(fields=["robot", "run_id"]),
        ]

    def clean(self):
        super().clean()
        if not self.session_key:
            raise ValidationError({"session_key": "session_key is required"})
        if not self.session_key.startswith(SESSION_KEY_PREFIXES):
            prefixes = ", ".join(SESSION_KEY_PREFIXES)
            raise ValidationError(
                {"session_key": f"Invalid prefix. session_key must start with one of: {prefixes}"}
            )

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    def touch(self):
        self.updated_at = timezone.now()
        self.save(update_fields=["updated_at"])


class RobotRun(models.Model):
    STATUS_PENDING = "pending"
    STATUS_RUNNING = "running"
    STATUS_SUCCESS = "success"
    STATUS_FAILED = "failed"
    STATUS_CANCELLED = "cancelled"
    STATUS_CHOICES = [
        (STATUS_PENDING, "Pending"),
        (STATUS_RUNNING, "Running"),
        (STATUS_SUCCESS, "Success"),
        (STATUS_FAILED, "Failed"),
        (STATUS_CANCELLED, "Cancelled"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    robot = models.ForeignKey(Robot, on_delete=models.CASCADE, related_name="runs")
    session = models.ForeignKey(
        RobotSession,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="runs",
    )

    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_PENDING)
    trigger_source = models.CharField(max_length=100, default="manual")
    trigger_payload = models.JSONField(default=dict, blank=True)

    usage = models.JSONField(default=dict, blank=True)
    execution_context = models.JSONField(default=dict, blank=True)
    output_data = models.JSONField(default=dict, blank=True)
    error_data = models.JSONField(default=dict, blank=True)

    cancel_requested_at = models.DateTimeField(null=True, blank=True, db_index=True)
    started_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="robot_runs_created",
    )

    class Meta:
        db_table = "robots_run"
        ordering = ["-started_at"]
        indexes = [
            models.Index(fields=["robot", "status"]),
            models.Index(fields=["robot", "-started_at"]),
            models.Index(fields=["session", "-started_at"]),
        ]

    def __str__(self) -> str:
        return f"Run {self.id} ({self.status})"

    @property
    def is_finished(self) -> bool:
        return self.status in {self.STATUS_SUCCESS, self.STATUS_FAILED, self.STATUS_CANCELLED}


class RobotMemory(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    robot = models.ForeignKey(Robot, on_delete=models.CASCADE, related_name="memories")
    session = models.ForeignKey(
        RobotSession,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="memories",
    )
    kind = models.CharField(max_length=64, default="fact")
    payload = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "robots_memory"
        indexes = [
            models.Index(fields=["robot", "kind", "-created_at"]),
            models.Index(fields=["session", "-created_at"]),
        ]


class RobotEvent(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    robot = models.ForeignKey(Robot, on_delete=models.CASCADE, related_name="events")
    run = models.ForeignKey(
        RobotRun,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="events",
    )
    session = models.ForeignKey(
        RobotSession,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="events",
    )
    event_type = models.CharField(max_length=128, db_index=True)
    payload = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        db_table = "robots_event"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["robot", "-created_at"]),
            models.Index(fields=["run", "-created_at"]),
            models.Index(fields=["event_type", "-created_at"]),
        ]
