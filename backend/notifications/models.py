"""
User notification preferences: subscribe/unsubscribe per channel and category.
"""
from __future__ import annotations

from django.conf import settings
from django.db import models


class UserNotificationPreference(models.Model):
    """
    Per-user subscription to notification types.
    Users can opt in/out of specific notification categories per channel.
    """
    CHANNEL_CHOICES = [
        ("email", "Email"),
        ("push", "Push"),
        ("in_app", "In-app"),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="notification_preferences",
    )
    tenant = models.ForeignKey(
        "tenancy.Tenant",
        on_delete=models.CASCADE,
        related_name="user_notification_preferences",
    )
    channel = models.CharField(max_length=20, choices=CHANNEL_CHOICES, db_index=True)
    category = models.CharField(
        max_length=80,
        db_index=True,
        help_text="Notification category e.g. ticket_assigned, flow_completed, deal_won, system_alerts",
    )
    subscribed = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "notifications_user_notification_preference"
        verbose_name = "User notification preference"
        verbose_name_plural = "User notification preferences"
        unique_together = ("user", "tenant", "channel", "category")
        ordering = ["user", "channel", "category"]
        indexes = [
            models.Index(fields=["user", "channel"]),
            models.Index(fields=["tenant", "category"]),
        ]

    def __str__(self) -> str:
        status = "subscribed" if self.subscribed else "unsubscribed"
        return f"{self.user_id} {self.channel}/{self.category} ({status})"
