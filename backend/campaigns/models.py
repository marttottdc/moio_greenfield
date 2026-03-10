import uuid
from django.db import models
from django.db.models import Q
from django.utils import timezone

from central_hub.models import Tenant, TenantScopedModel


# Create your models here.
class Channel(models.TextChoices):
    EMAIL = "email", "Email"
    WHATSAPP = "whatsapp", "WhatsApp"
    TELEGRAM = "telegram", "Telegram"
    SMS = "sms", "SMS"


class Kind(models.TextChoices):
    EXPRESS = "express", "Express"
    ONE_SHOT = "one_shot", "One Shot"
    DRIP = "drip", "Drip"
    PLANNED = "planned", "Planned"


class Status(models.TextChoices):
    DRAFT = "draft", "Draft"
    READY = "ready", "Ready"
    SCHEDULED = "scheduled", "Scheduled"
    ACTIVE = "active", "Active"
    ENDED = "ended", "Ended"
    ARCHIVED = "archived", "Archived"


class AudienceKind(models.TextChoices):
    STATIC = "static", "Static list"
    DYNAMIC = "dynamic", "Dynamic filter"  # optional, leave if you’ll add rules later


class Audience(TenantScopedModel):
    """
    A reusable list of recipients.
    It can be filled from the Contact table or from any ad‑hoc import (CSV, XLSX, etc.).
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    kind = models.CharField(max_length=10, choices=AudienceKind.choices, default=AudienceKind.STATIC)
    rules = models.JSONField(blank=True, null=True)
    # cached count, so you don’t run .count() on a million‑row table for every dashboard
    size = models.PositiveIntegerField(default=0, editable=False)

    materialized_at = models.DateTimeField(null=True, blank=True)
    created = models.DateTimeField(auto_now_add=True)
    updated = models.DateTimeField(auto_now=True)
    is_draft = models.BooleanField(default=True)

    # ergonomic M2M via a single through-table
    contacts = models.ManyToManyField(
        "crm.Contact",
        through="AudienceMembership",
        related_name="audiences",
        blank=True,
    )

    def __str__(self):
        return self.name


class AudienceMembership(TenantScopedModel):
    """Unified membership. Managed manually for STATIC, programmatically for DYNAMIC."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    audience = models.ForeignKey(Audience, on_delete=models.CASCADE, related_name="membership")
    contact = models.ForeignKey("crm.Contact", on_delete=models.CASCADE, related_name="audience_membership")
    created = models.DateTimeField(auto_now_add=True)
    updated = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["audience", "contact"], name="uq_audience_contact_once"),
        ]
        indexes = [models.Index(fields=["audience"]), models.Index(fields=["contact"])]


class Campaign(TenantScopedModel):

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)

    channel = models.CharField(max_length=10,choices=Channel.choices,)
    kind = models.CharField(max_length=10, choices=Kind.choices,)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.DRAFT,)

    audience = models.ForeignKey(Audience, on_delete=models.PROTECT, related_name="campaigns", null=True, blank=True, help_text="Required before campaign can be activated")
    # stores {} unless you pass something
    config = models.JSONField(default=dict, blank=True, help_text="Arbitrary per‑campaign settings (per channel, templates, A/B flags, etc.)")
    sent = models.PositiveIntegerField(default=0)
    opened = models.PositiveIntegerField(default=0)
    responded = models.PositiveIntegerField(default=0)
    created = models.DateTimeField(auto_now_add=True)
    updated = models.DateTimeField(auto_now=True)

    # ─── Dunder methods ───────────────────────────────────────────────────────
    def __str__(self):
        return self.name
    
    def can_launch(self):
        """Check if campaign has all required fields to be launched"""
        return bool(self.audience and self.audience.size > 0)
    
    def launch_validation_errors(self):
        """Return list of validation errors preventing launch"""
        errors = []
        if not self.audience:
            errors.append("Campaign must have an audience selected")
        elif self.audience.size == 0:
            errors.append("Selected audience is empty")
        return errors


class CampaignDataStatus(models.TextChoices):
    PENDING = "pending", "Pending"      # queued, not yet sent
    SENT = "sent", "Sent"         # accepted by provider
    DELIVERED = "delivered", "Delivered"    # confirmed delivered/read
    FAILED = "failed", "Failed"       # hard error
    SKIPPED = "skipped", "Skipped"      # e.g. missing vars


class CampaignData(TenantScopedModel):
    """
    One row = one personalised message ready to be fired.

    • Holds the rendered *variable* payload for the chosen template
    • Knows its recipient (AudienceMember) and parent Campaign
    • Tracks lifecycle (queued → sent → delivered/failed)
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    campaign = models.ForeignKey("Campaign", on_delete=models.CASCADE, related_name="data_rows",)

    variables = models.JSONField()

    status = models.CharField(max_length=10, choices=CampaignDataStatus.choices, default=CampaignDataStatus.PENDING, db_index=True,)
    attempts = models.PositiveSmallIntegerField(default=0)   # retry counter
    last_error = models.TextField(blank=True)

    scheduled_at = models.DateTimeField(default=timezone.now, db_index=True)
    sent_at = models.DateTimeField(null=True, blank=True)
    delivered_at = models.DateTimeField(null=True, blank=True)

    created = models.DateTimeField(auto_now_add=True)
    updated = models.DateTimeField(auto_now=True)

    result = models.JSONField(null=True, blank=True)
    job = models.UUIDField(null=True, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=["campaign", "status"]),
            models.Index(fields=["scheduled_at"]),
        ]

    # handy helper ---------------------------------------------------
    def mark(self, new_status: str, error: str | None = None):
        self.status = new_status
        self.last_error = error or ""
        ts = timezone.now()
        if new_status == CampaignDataStatus.SENT:
            self.sent_at = ts
        elif new_status == CampaignDataStatus.DELIVERED:
            self.delivered_at = ts
        self.save(update_fields=["status", "last_error", "sent_at", "delivered_at", "updated"])


class CampaignDataStaging(models.Model):
    """
    One record per import (Excel, CSV, API, etc.)
    Stores the full dataset as JSON until mapped/processed.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="campaign_data_staging")
    campaign_id = models.UUIDField(null=True, blank=True)  # optional link to a draft campaign

    # Full file contents
    raw_data = models.JSONField()   # e.g. df.to_json(orient="records") parsed into Python list/dict
    mapped_data = models.JSONField(null=True, blank=True)  # optional shaped/enriched version

    import_source = models.CharField(max_length=100, blank=True, default="")
    original_filename = models.CharField(max_length=255, blank=True, default="")
    row_count = models.PositiveIntegerField(null=True, blank=True)  # useful for quick stats
    errors = models.JSONField(null=True, blank=True)  # validation summary at file-level

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Import {self.id} ({self.row_count or 0} rows)"
