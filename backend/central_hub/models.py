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

    class Meta:
        db_table = 'platform_configuration'
        verbose_name = "Platform Configuration"
        verbose_name_plural = "Platform Configurations"
