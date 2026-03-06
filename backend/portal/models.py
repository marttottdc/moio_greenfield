import hashlib
import re
import secrets
import string
import uuid

from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin, Group
from django.core.validators import MinValueValidator
from django.db import models
from django.db.models import ForeignKey, Q
from django.utils import timezone
from django.utils.text import slugify
from django_tenants.models import DomainMixin, TenantMixin

from portal.context_utils import current_tenant


def _default_schema_name(nombre: str | None, subdomain: str | None, tenant_code: uuid.UUID | None) -> str:
    seed = str(subdomain or nombre or tenant_code or "tenant").strip().lower()
    normalized = slugify(seed).replace("-", "_")
    normalized = re.sub(r"[^a-z0-9_]", "_", normalized)
    normalized = re.sub(r"_+", "_", normalized).strip("_")
    if not normalized:
        normalized = f"tenant_{str(tenant_code or uuid.uuid4()).replace('-', '_')}"
    if normalized[0].isdigit():
        normalized = f"t_{normalized}"
    return normalized[:63]


class Tenant(TenantMixin, models.Model):

    class Plan(models.TextChoices):
        FREE = 'free', 'Free'
        PRO = 'pro', 'Pro'
        BUSINESS = 'business', 'Business'

    nombre = models.CharField(max_length=150, null=False)
    enabled = models.BooleanField(default=True)
    domain = models.CharField(max_length=150, null=False)
    subdomain = models.CharField(max_length=100, null=True, blank=True, unique=True, db_index=True)
    plan = models.CharField(max_length=20, choices=Plan.choices, default=Plan.FREE)
    tenant_code = models.UUIDField(default=uuid.uuid4, editable=True, unique=True)
    created = models.DateTimeField(default=timezone.now)

    # Entitlements (tier-based features and limits); seeded from plan on create, ops can override.
    features = models.JSONField(
        default=dict,
        blank=True,
        help_text="Feature flags e.g. {crm_contacts_read: true, users_manage: false}",
    )
    limits = models.JSONField(
        default=dict,
        blank=True,
        help_text="Limits e.g. {seats: 5, agents: 2, flows: 20}",
    )
    ui = models.JSONField(
        default=dict,
        blank=True,
        help_text="Optional UI hints for frontend",
    )
    entitlements_updated_at = models.DateTimeField(null=True, blank=True, auto_now=True)

    @property
    def primary_domain(self) -> str:
        host = str(self.domain or "").strip()
        subdomain = str(self.subdomain or "").strip()
        if host and subdomain:
            return f"{subdomain}.{host}"
        return host

    def save(self, *args, **kwargs):
        if not self.schema_name:
            self.schema_name = _default_schema_name(
                self.nombre,
                self.subdomain,
                self.tenant_code,
            )
        super().save(*args, **kwargs)

    def __str__(self):
        return f'{self.pk} : {self.nombre}'


class TenantDomain(DomainMixin):
    class Meta:
        db_table = "portal_tenant_domain"
        verbose_name = "Tenant domain"
        verbose_name_plural = "Tenant domains"


class TenantManager(models.Manager):
    def get_queryset(self):
        tenant = current_tenant.get()
        # print(f'Current tenant in Tenant Manager is: {tenant}')
        if tenant:
            return super().get_queryset().filter(tenant=tenant)
        return super().get_queryset()


class ContentBlockManager(models.Manager):
    """Manager that exposes public blocks regardless of the active tenant."""

    def get_queryset(self):
        tenant = current_tenant.get()
        queryset = super().get_queryset()

        visibility_enum = getattr(self.model, "Visibility", None)
        public_value = getattr(visibility_enum, "PUBLIC", "public")

        if tenant:
            return queryset.filter(Q(visibility=public_value) | Q(tenant=tenant))
        return queryset.filter(visibility=public_value)


class TenantScopedModel(models.Model):
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE)
    objects = TenantManager()  # Use the custom manager

    class Meta:
        abstract = True


class PortalConfiguration (models.Model):

    site_name = models.CharField(max_length=100, null=True)
    company = models.CharField(max_length=100, null=True)
    my_url = models.URLField(default='http://127.0.0.1:8000/')
    logo = models.ImageField(upload_to='portal/', blank=True)
    favicon = models.ImageField(upload_to='portal/', blank=True)
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
        db_table = 'portal_configuration'
        verbose_name_plural = "Portal Configurations"


class ConversationHandler(models.TextChoices):
    CHATBOT = 'chatbot', 'Chatbot'
    ASSISTANT = 'assistant', 'Assistant'
    AGENT = 'agent', 'Agent'


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
    conversation_handler = models.CharField(max_length=40, choices=ConversationHandler.choices, default=ConversationHandler.ASSISTANT)
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

    def save(self, *args, **kwargs):
        """Override save to sync integration fields to IntegrationConfig."""
        super().save(*args, **kwargs)
        self._sync_to_integration_configs()

    def _sync_to_integration_configs(self) -> None:
        """
        Write-through sync: Extract integration fields and sync to IntegrationConfig.
        This ensures IntegrationConfig always has the latest data.
        """
        from portal.integrations.models import IntegrationConfig
        from portal.integrations.registry import INTEGRATION_REGISTRY

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


class Document(TenantScopedModel):
    file = models.FileField(upload_to='documents/')


class UserManager(BaseUserManager):
    def create_user(self, email, username, password=None, **extra_fields):
        if not email:
            raise ValueError('The email must be set')
        if not username:
            raise ValueError('The username must be set')
        email = self.normalize_email(email)
        user = self.model(email=email, username=username, **extra_fields)  # Add username here
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, username, password=None, **extra_fields):
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        extra_fields.setdefault('is_active', True)
        # return self.create_user(email, username, password, **extra_fields)

        if extra_fields.get('is_staff') is not True:
            raise ValueError('Superuser must have is_staff=True.')

        if extra_fields.get('is_superuser') is not True:
            raise ValueError('Superuser must have is_superuser=True.')

        # return self.create_user(email, password, **extra_fields)
        return self.create_user(email, username, password, **extra_fields)


class MoioUser(AbstractBaseUser, PermissionsMixin):
    email = models.EmailField(unique=True)
    username = models.CharField(max_length=150, unique=True)
    first_name = models.CharField(max_length=30, blank=True)
    last_name = models.CharField(max_length=150, blank=True)
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, null=True)
    phone = models.CharField(max_length=20, blank=True)
    is_active = models.BooleanField(default=True)
    last_login = models.DateTimeField(blank=True, null=True)
    created = models.DateTimeField(default=timezone.now)
    is_staff = models.BooleanField(default=False)
    is_superuser = models.BooleanField(default=False)
    avatar = models.ImageField(upload_to='avatars/', default='avatars/default-avatar.png')
    preferences = models.JSONField(default=dict, blank=True)

    groups = models.ManyToManyField(
        'auth.Group',
        verbose_name='groups',
        blank=True,
        help_text='The groups this user belongs to. A user will get all permissions granted to each of their groups.',
        related_name="moiouser_set",
        related_query_name="moiouser",
    )
    user_permissions = models.ManyToManyField(
        'auth.Permission',
        verbose_name='user permissions',
        blank=True,
        help_text='Specific permissions for this user.',
        related_name="moiouser_set",
        related_query_name="moiouser",
    )

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['username']

    objects = UserManager()

    def __str__(self):
        return self.email

    def get_short_name(self):
        return self.first_name or self.username

    @property
    def name(self):
        return self.first_name or self.username


class UserProfile(models.Model):
    """
    Product identity and UX state for a user (OneToOne MoioUser).
    """
    user = models.OneToOneField(
        MoioUser,
        on_delete=models.CASCADE,
        related_name="profile",
    )
    display_name = models.CharField(max_length=200, blank=True)
    title = models.CharField(max_length=100, blank=True)
    department = models.CharField(max_length=100, blank=True)
    locale = models.CharField(max_length=20, blank=True, default="en")
    timezone = models.CharField(max_length=60, blank=True, default="UTC")
    onboarding_state = models.CharField(max_length=50, blank=True, default="pending")
    default_landing = models.CharField(max_length=200, blank=True, default="/dashboard")
    ui_preferences = models.JSONField(default=dict, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "portal_user_profile"
        verbose_name = "User profile"
        verbose_name_plural = "User profiles"

    def __str__(self):
        return f"Profile for {self.user.email}"


class AuthSession(models.Model):
    user = models.OneToOneField(MoioUser, on_delete=models.CASCADE, related_name="auth_session")
    refresh_token = models.CharField(max_length=255, unique=True)
    session_token = models.CharField(max_length=255, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    revoked_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "portal_auth_session"

    def revoke(self, save: bool = True) -> None:
        if not self.revoked_at:
            self.revoked_at = timezone.now()
            if save:
                self.save(update_fields=["revoked_at"])


class UserApiKey(models.Model):
    """
    Single API key per user for automated service access.
    Users can create/revoke their key on demand. Plain key is shown only once on creation.
    """
    user = models.OneToOneField(
        MoioUser,
        on_delete=models.CASCADE,
        related_name="api_key",
    )
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE)

    key_hash = models.CharField(max_length=64, db_index=True)
    name = models.CharField(max_length=100, default="API Key")

    created_at = models.DateTimeField(auto_now_add=True)
    last_used_at = models.DateTimeField(null=True, blank=True)
    expires_at = models.DateTimeField(null=True, blank=True)

    is_active = models.BooleanField(default=True)
    scopes = models.JSONField(default=list, blank=True)

    class Meta:
        db_table = "portal_userapikey"
        verbose_name = "User API Key"
        verbose_name_plural = "User API Keys"
        ordering = ["-created_at"]

    def __str__(self):
        return f"API Key for {self.user.email}"

    @property
    def masked_key(self):
        """Return masked version for display (e.g. moio_abc1...xyz9)."""
        if not self.key_hash:
            return ""
        return "moio_****...****"

    def generate_key(self):
        """Generate a secure random API key. Caller must display plain key once."""
        chars = string.ascii_letters + string.digits
        random_part = "".join(secrets.choice(chars) for _ in range(32))
        plain_key = f"moio_{random_part}"
        self.key_hash = hashlib.sha256(plain_key.encode()).hexdigest()
        return plain_key

    def verify_key(self, provided_key):
        """Verify if provided key matches this API key."""
        return self.key_hash == hashlib.sha256(provided_key.encode()).hexdigest()


class Instruction(TenantScopedModel):
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE)
    key = models.CharField(max_length=100, null=False)
    prompt = models.TextField(blank=True)


class Notification(TenantScopedModel):
    id = models.UUIDField(default=uuid.uuid4, primary_key=True)
    type = models.CharField(max_length=40)
    message = models.CharField(max_length=250)
    created = models.DateTimeField(auto_now=True)
    source = models.CharField(max_length=40)
    severity = models.CharField(max_length=40)
    to = models.CharField(max_length=150, default='all')
    read = models.BooleanField(default=False)

    def __str__(self):
        return f'{self.source} - {self.message}'


class TargetZone(models.TextChoices):
    desktop_content = 'moio-desktop-content', 'Desktop Content'
    modal = 'dialog', 'Modal Dialog'
    top_nav_bar = 'moio-top-navbar', 'Top Navbar'
    full = 'moio-full-content', 'Full Content'
    side = 'moio-side-content', 'Side Content'


class AppConfig(models.Model):
    id = models.UUIDField(default=uuid.uuid4, primary_key=True)
    name = models.CharField(max_length=250)
    description = models.CharField(max_length=250)
    icon = models.CharField(max_length=250, null=True, blank=True)
    enabled = models.BooleanField(default=True)
    tenants = models.ManyToManyField(Tenant)
    default_screen = models.CharField(max_length=250, default="#", blank=True)

    def __str__(self):
        return self.name


class AppMenu(models.Model):
    id = models.UUIDField(default=uuid.uuid4, primary_key=True)
    app = models.CharField(max_length=40)
    url = models.CharField(max_length=250)
    type = models.CharField(max_length=40)
    enabled = models.BooleanField(default=True)
    title = models.CharField(max_length=250)
    description = models.CharField(max_length=250)
    perm_group = models.CharField(max_length=250)
    target_area = models.CharField(max_length=250, choices=TargetZone.choices, default=TargetZone.desktop_content,)
    icon = models.CharField(max_length=250, null=True, blank=True)
    context = models.CharField(max_length=250, null=True, blank=True)

    def __str__(self):
        return self.title


class ComponentTemplate(TenantScopedModel):
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE)
    name = models.CharField(max_length=150)
    slug = models.SlugField(max_length=150)
    description = models.TextField(blank=True)
    template_path = models.CharField(max_length=255)
    context_schema = models.JSONField(blank=True, default=dict)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('tenant', 'slug')
        verbose_name = 'Component template'
        verbose_name_plural = 'Component templates'

    def __str__(self):
        return f"{self.name} ({self.slug})"


class ContentBlock(TenantScopedModel):
    class Visibility(models.TextChoices):
        PUBLIC = 'public', 'Public'
        TENANT_ONLY = 'tenant_only', 'Tenant only'

    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE)
    component = models.ForeignKey(ComponentTemplate, related_name='blocks', on_delete=models.CASCADE)
    group = models.SlugField(max_length=150)
    title = models.CharField(max_length=150, blank=True)
    order = models.PositiveIntegerField(default=0, validators=[MinValueValidator(0)])
    context = models.JSONField(blank=True, default=dict)
    visibility = models.CharField(
        max_length=32,
        choices=Visibility.choices,
        default=Visibility.TENANT_ONLY,
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = ContentBlockManager()
    tenant_objects = TenantManager()
    all_objects = models.Manager()

    class Meta:
        ordering = ('order', 'id')
        unique_together = ('tenant', 'group', 'order')

    def __str__(self):
        return f"{self.group} :: {self.component}"
