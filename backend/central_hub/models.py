import uuid

from django.db import models
from django.db.models import Q
from django.utils import timezone

from tenancy.models import (
    AuthSession,
    MoioUser,
    Tenant,
    TenantDomain,
    TenantManager,
    TenantScopedModel,
    UserApiKey,
    UserProfile,
)


PROVISIONING_STAGE_CHOICES = (
    ("tenant_creation", "Tenant creation"),
    ("tenant_seeding", "Tenant seeding"),
    ("primary_user_creation", "Primary user creation"),
)

PROVISIONING_STATUS_CHOICES = (
    ("pending", "Pending"),
    ("running", "Running"),
    ("success", "Success"),
    ("failure", "Failure"),
)


def default_provisioning_stages():
    return {
        "tenant_creation": {"status": "pending", "started_at": None, "finished_at": None, "error": ""},
        "tenant_seeding": {"status": "pending", "started_at": None, "finished_at": None, "error": ""},
        "primary_user_creation": {"status": "pending", "started_at": None, "finished_at": None, "error": ""},
    }


class PlatformConfiguration(models.Model):
    """Global platform settings. Managed via Platform Admin."""

    site_name = models.CharField(max_length=100, null=True)
    company = models.CharField(max_length=100, null=True)
    my_url = models.URLField(default='http://127.0.0.1:8000/')
    logo = models.ImageField(upload_to='central_hub/', blank=True)
    favicon = models.ImageField(upload_to='central_hub/', blank=True)
    whatsapp_webhook_token = models.CharField(max_length=100, null=True, blank=True, default="")
    whatsapp_webhook_redirect = models.URLField(default='http://127.0.0.1:8000/')
    fb_system_token = models.CharField(max_length=500, null=True, blank=True, default="")
    fb_moio_bot_app_id = models.CharField(max_length=100, null=True, blank=True, default="")
    fb_moio_business_manager_id = models.CharField(max_length=100, null=True, blank=True, default="")
    fb_moio_bot_app_secret = models.CharField(max_length=100, null=True, blank=True, default="")
    fb_moio_bot_configuration_id = models.CharField(max_length=100, null=True, blank=True, default="")
    # OAuth client configuration
    google_oauth_client_id = models.CharField(max_length=200, null=True, blank=True, default="")
    google_oauth_client_secret = models.CharField(max_length=200, null=True, blank=True, default="")
    microsoft_oauth_client_id = models.CharField(max_length=200, null=True, blank=True, default="")
    microsoft_oauth_client_secret = models.CharField(max_length=200, null=True, blank=True, default="")
    # Shopify App (embedded app OAuth)
    shopify_client_id = models.CharField(max_length=200, null=True, blank=True, default="")
    shopify_client_secret = models.CharField(max_length=200, null=True, blank=True, default="")

    class Meta:
        db_table = 'platform_configuration'
        verbose_name = "Platform Configuration"
        verbose_name_plural = "Platform Configurations"


class Plan(models.Model):
    """
    Plan definitions for tenant subscription tiers. Managed in Platform Admin.
    Tenant.plan stores the plan key; entitlements_defaults use these keys (free, pro, business by default).
    """
    key = models.CharField(max_length=40, unique=True, db_index=True)
    name = models.CharField(max_length=100)
    display_order = models.IntegerField(default=0)
    is_active = models.BooleanField(default=True)
    is_self_provision_default = models.BooleanField(default=False)
    pricing_policy = models.JSONField(
        default=dict,
        blank=True,
        help_text="Pricing configuration (base fees, per-unit pricing, included units, currency).",
    )
    entitlement_policy = models.JSONField(
        default=dict,
        blank=True,
        help_text="Plan policy (trial/grace durations, assignment limits, module constraints).",
    )

    class Meta:
        db_table = "platform_plan"
        verbose_name = "Plan"
        verbose_name_plural = "Plans"
        ordering = ["display_order", "key"]

    def __str__(self):
        return f"{self.key}: {self.name}"


class Capability(models.Model):
    """
    Granular permission (e.g. crm_contacts_read, users_manage).
    Roles are combinations of these; used for eff.can() after intersecting with tenant plan.
    """
    key = models.CharField(max_length=80, unique=True, db_index=True)
    label = models.CharField(max_length=200)
    description = models.TextField(blank=True, default="")

    class Meta:
        db_table = "platform_capability"
        verbose_name = "Capability"
        verbose_name_plural = "Capabilities"
        ordering = ["key"]

    def __str__(self):
        return self.label or self.key


class Role(models.Model):
    """
    Role = combination of capabilities. Stored in DB for Platform Admin editing.
    slug is used as Django Group name so tenant admins assign users to a group (one role per user).
    """
    name = models.CharField(max_length=100)
    slug = models.SlugField(max_length=80, unique=True, db_index=True)
    display_order = models.IntegerField(default=0)
    capabilities = models.ManyToManyField(
        Capability,
        related_name="roles",
        blank=True,
        help_text="Capabilities granted by this role (intersected with tenant plan).",
    )

    class Meta:
        db_table = "platform_role"
        verbose_name = "Role"
        verbose_name_plural = "Roles"
        ordering = ["display_order", "slug"]

    def __str__(self):
        return self.name or self.slug

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        from django.contrib.auth.models import Group
        Group.objects.get_or_create(name=self.slug)


class ProvisioningJob(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    status = models.CharField(max_length=20, choices=PROVISIONING_STATUS_CHOICES, default="pending")
    current_stage = models.CharField(max_length=40, choices=PROVISIONING_STAGE_CHOICES, blank=True, default="")
    stages = models.JSONField(default=default_provisioning_stages, blank=True)
    requested_name = models.CharField(max_length=150)
    requested_email = models.EmailField()
    requested_username = models.CharField(max_length=150)
    requested_subdomain = models.CharField(max_length=100, blank=True, default="")
    requested_domain = models.CharField(max_length=150, blank=True, default="")
    requested_locale = models.CharField(max_length=10, default="es")
    tenant = models.ForeignKey(Tenant, null=True, blank=True, on_delete=models.SET_NULL, related_name="provisioning_jobs")
    user = models.ForeignKey(MoioUser, null=True, blank=True, on_delete=models.SET_NULL, related_name="provisioning_jobs")
    error_message = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "platform_provisioning_job"
        verbose_name = "Provisioning job"
        verbose_name_plural = "Provisioning jobs"
        ordering = ["-created_at"]

    def _touch_stage(self, stage: str) -> dict:
        stages = dict(self.stages or default_provisioning_stages())
        payload = dict(stages.get(stage) or {})
        stages[stage] = payload
        self.stages = stages
        return payload

    def mark_stage_running(self, stage: str) -> None:
        payload = self._touch_stage(stage)
        payload["status"] = "running"
        payload["started_at"] = timezone.now().isoformat()
        payload["finished_at"] = None
        payload["error"] = ""
        self.current_stage = stage
        self.status = "running"
        self.error_message = ""
        self.save(update_fields=["stages", "current_stage", "status", "error_message", "updated_at"])

    def mark_stage_success(self, stage: str, *, final: bool = False) -> None:
        payload = self._touch_stage(stage)
        payload["status"] = "success"
        payload["finished_at"] = timezone.now().isoformat()
        payload["error"] = ""
        self.current_stage = stage
        self.status = "success" if final else "running"
        self.error_message = ""
        self.save(update_fields=["stages", "current_stage", "status", "error_message", "updated_at"])

    def mark_stage_failure(self, stage: str, error_message: str) -> None:
        payload = self._touch_stage(stage)
        payload["status"] = "failure"
        payload["finished_at"] = timezone.now().isoformat()
        payload["error"] = str(error_message or "Provisioning failed")
        self.current_stage = stage
        self.status = "failure"
        self.error_message = payload["error"]
        self.save(update_fields=["stages", "current_stage", "status", "error_message", "updated_at"])


class PlatformNotificationSettings(models.Model):
    """
    Platform-wide notification settings (PWA, in-app, flows, agent console).
    Shared across the whole platform; single row (singleton). Managed via Platform Admin.
    """
    title = models.CharField(max_length=200, default="Moio", blank=True)
    icon_url = models.URLField(max_length=500, blank=True, default="")
    badge_url = models.URLField(max_length=500, blank=True, default="")
    require_interaction = models.BooleanField(default=False)
    renotify = models.BooleanField(default=False)
    silent = models.BooleanField(default=False)
    test_title = models.CharField(max_length=200, default="Moio test notification", blank=True)
    test_body = models.TextField(default="Notifications are configured for this browser.", blank=True)

    class Meta:
        db_table = "platform_notification_settings"
        verbose_name = "Platform notification settings"
        verbose_name_plural = "Platform notification settings"
