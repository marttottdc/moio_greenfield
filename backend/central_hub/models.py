from django.db import models
from django.db.models import Q

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
