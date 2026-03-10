import uuid

from django.db import models
from django.db.models import Q
from django.utils import timezone
from django.utils.text import slugify

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


class TenantConfiguration(TenantScopedModel):
    tenant = models.ForeignKey(Tenant, related_name="configuration", on_delete=models.CASCADE)

    google_integration_enabled = models.BooleanField(default=False)
    google_api_key = models.CharField(max_length=400, blank=True, default="")

    openai_integration_enabled = models.BooleanField(default=False)
    openai_api_key = models.CharField(max_length=400, blank=True, default="")
    openai_max_retries = models.IntegerField(default=5)
    openai_default_model = models.CharField(max_length=100, blank=True, default="gpt-4o-mini")
    openai_embedding_model = models.CharField(max_length=100, blank=True, default="text-embedding-3-small")

    whatsapp_integration_enabled = models.BooleanField(default=False)
    whatsapp_token = models.CharField(max_length=500, null=True, blank=True, default="")
    whatsapp_url = models.CharField(max_length=200, null=True, blank=True, default="")
    whatsapp_phone_id = models.CharField(max_length=100, null=True, blank=True, default="")
    whatsapp_business_account_id = models.CharField(max_length=100, null=True, blank=True, default="")
    whatsapp_name = models.CharField(max_length=100, null=False, unique=True, blank=True, default="")
    whatsapp_catalog_id = models.CharField(max_length=100, null=True, blank=True, default="")

    hiringroom_integration_enabled = models.BooleanField(default=False)
    hiringroom_client_id = models.CharField(max_length=200, null=True, blank=True, default="")
    hiringroom_client_secret = models.CharField(max_length=200, null=True, blank=True, default="")
    hiringroom_username = models.CharField(max_length=200, null=True, blank=True, default="")
    hiringroom_password = models.CharField(max_length=200, null=True, blank=True, default="")

    psigma_integration_enabled = models.BooleanField(default=False)
    psigma_user = models.CharField(max_length=200, null=True, blank=True, default="")
    psigma_password = models.CharField(max_length=200, null=True, blank=True, default="")
    psigma_token = models.CharField(max_length=200, null=True, blank=True, default="")
    psigma_url = models.CharField(max_length=200, null=True, blank=True, default="")

    zetaSoftware_integration_enabled = models.BooleanField(default=False)
    zetaSoftware_dev_code = models.CharField(max_length=200, null=True, blank=True, default="")
    zetaSoftware_dev_key = models.CharField(max_length=200, null=True, blank=True, default="")
    zetaSoftware_company_code = models.CharField(max_length=200, null=True, blank=True, default="")
    zetaSoftware_company_key = models.CharField(max_length=200, null=True, blank=True, default="")

    woocommerce_integration_enabled = models.BooleanField(default=False)
    woocommerce_site_url = models.CharField(max_length=500, null=True, blank=True, default="")
    woocommerce_consumer_key = models.CharField(max_length=200, null=True, blank=True, default="")
    woocommerce_consumer_secret = models.CharField(max_length=200, null=True, blank=True, default="")

    wordpress_integration_enabled = models.BooleanField(default=False)
    wordpress_username = models.CharField(max_length=200, null=True, blank=True, default="")
    wordpress_app_password = models.CharField(max_length=200, null=True, blank=True, default="")
    wordpress_site_url = models.CharField(max_length=500, null=True, blank="", default="")

    dac_integration_enabled = models.BooleanField(default=False)
    dac_user = models.CharField(max_length=200, null=True, blank=True, default="")
    dac_password = models.CharField(max_length=200, null=True, blank=True, default="")
    dac_rut = models.CharField(max_length=200, null=True, blank=True, default="")
    dac_sender_name = models.CharField(max_length=200, null=True, blank=True, default="")
    dac_sender_phone = models.CharField(max_length=200, null=True, blank=True, default="")
    dac_base_url = models.CharField(max_length=400, null=True, blank=True, default="")
    dac_notification_list = models.TextField(null=True, blank=True, default="monitoring@moio.ai,")
    dac_tracking_period = models.IntegerField(default=30)
    dac_polling_interval = models.IntegerField(default=30)

    assistants_enabled = models.BooleanField(default=False)
    assistants_default_id = models.CharField(max_length=200, null=True, blank=True, default="")
    conversation_handler = models.CharField(
        max_length=40,
        choices=[('chatbot', 'Chatbot'), ('assistant', 'Assistant'), ('agent', 'Agent')],
        default='assistant',
    )
    assistant_smart_reply_enabled = models.BooleanField(default=False)
    assistant_output_formatting_instructions = models.TextField(null=True, blank=True, default="")
    assistant_output_schema = models.TextField(null=True, blank=True, default="")
    assistants_inactivity_limit = models.IntegerField(default=30)
    chatbot_enabled = models.BooleanField(default=False)
    default_agent_id = models.URLField(null=True, blank=True, default="")
    agent_allow_reopen_session = models.BooleanField(default=False)
    agent_reopen_threshold = models.IntegerField(default=360)

    mercadopago_integration_enabled = models.BooleanField(default=False)
    mercadopago_webhook_secret = models.CharField(max_length=400, null=True, blank=True, default="")
    mercadopago_public_key = models.CharField(max_length=400, null=True, blank=True, default="")
    mercadopago_access_token = models.CharField(max_length=400, null=True, blank=True, default="")
    mercadopago_client_id = models.CharField(max_length=200, null=True, blank=True, default="")
    mercadopago_client_secret = models.CharField(max_length=200, null=True, blank=True, default="")

    smtp_integration_enabled = models.BooleanField(default=False)
    smtp_host = models.CharField(max_length=200, null=True, blank=True, default="")
    smtp_port = models.IntegerField(default=465)
    smtp_use_tls = models.BooleanField(default=True)
    smtp_user = models.CharField(max_length=200, null=True, blank=True, default="")
    smtp_password = models.CharField(max_length=200, null=True, blank=True, default="")
    smtp_from = models.CharField(max_length=200, null=True, blank=True, default="")

    default_notification_list = models.TextField(null=True, blank=True, default="martin@moio.ai,", help_text="Insert valid email addresses separated by comma")
    organization_currency = models.CharField(max_length=3, default="USD")
    organization_timezone = models.CharField(max_length=100, default="UTC")
    organization_date_format = models.CharField(max_length=20, default="DD/MM/YYYY")
    organization_time_format = models.CharField(max_length=10, default="24h")

    class Meta:
        db_table = 'tenant_configuration'
        verbose_name_plural = "Tenant Configurations"

    def __str__(self):
        return f'{self.tenant} config'

    def _ensure_unique_whatsapp_name(self) -> None:
        if str(self.whatsapp_name or "").strip():
            return

        tenant_hint = (
            getattr(self.tenant, "subdomain", None)
            or getattr(self.tenant, "schema_name", None)
            or str(self.tenant_id or "tenant")
        )
        normalized_hint = slugify(str(tenant_hint)).replace("-", "") or "tenant"
        base = f"tenant-{normalized_hint}"[:100]
        candidate = base
        if type(self).objects.filter(whatsapp_name=candidate).exclude(pk=self.pk).exists():
            suffix = uuid.uuid4().hex[:8]
            candidate = f"{base[:91]}-{suffix}"
        self.whatsapp_name = candidate

    def save(self, *args, **kwargs):
        """Override save to sync integration fields to IntegrationConfig."""
        self._ensure_unique_whatsapp_name()
        super().save(*args, **kwargs)
        self._sync_to_integration_configs()

    def _sync_to_integration_configs(self) -> None:
        """
        Write-through sync: Extract integration fields and sync to IntegrationConfig.
        This ensures IntegrationConfig always has the latest data.
        """
        from central_hub.integrations.models import IntegrationConfig
        from central_hub.integrations.registry import INTEGRATION_REGISTRY

        for slug, definition in INTEGRATION_REGISTRY.items():
            config_data = {}
            enabled = False

            if definition.enabled_field_legacy:
                enabled = getattr(self, definition.enabled_field_legacy, False)

            for field_def in definition.fields:
                if field_def.legacy_field:
                    value = getattr(self, field_def.legacy_field, None)
                    if value is not None:
                        config_data[field_def.name] = value

            IntegrationConfig.objects.update_or_create(
                tenant=self.tenant,
                slug=slug,
                instance_id="default",
                defaults={
                    "enabled": enabled,
                    "config": config_data,
                    "name": definition.name,
                }
            )
