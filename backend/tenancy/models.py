"""
Tenancy models: Tenant, TenantDomain, TenantScopedModel, MoioUser, UserProfile, AuthSession, UserApiKey,
IntegrationDefinition, TenantIntegration.
"""
from __future__ import annotations

import hashlib
import re
import secrets
import string
import uuid

from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.core.validators import RegexValidator
from django.db import models
from django.db.models import Q
from django.utils import timezone
from django.utils.text import slugify
from django_tenants.models import DomainMixin, TenantMixin

from tenancy.context_utils import current_tenant
from tenancy.validators import validate_subdomain_rfc


SCHEMA_RE = RegexValidator(
    regex=r"^[a-z0-9][a-z0-9_]{0,62}$",
    message="Schema name must match [a-z0-9][a-z0-9_]{0,62}",
)


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
        FREE = "free", "Free"
        PRO = "pro", "Pro"
        BUSINESS = "business", "Business"

    nombre = models.CharField(max_length=150, null=False)
    enabled = models.BooleanField(default=True)
    domain = models.CharField(max_length=150, null=False)
    subdomain = models.CharField(max_length=100, null=True, blank=True, unique=True, db_index=True)
    plan = models.CharField(max_length=20, choices=Plan.choices, default=Plan.FREE)
    tenant_code = models.UUIDField(default=uuid.uuid4, editable=True, unique=True)
    created = models.DateTimeField(default=timezone.now)

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
        if self.subdomain:
            try:
                validate_subdomain_rfc(self.subdomain)
            except ValueError as e:
                from django.core.exceptions import ValidationError
                raise ValidationError({"subdomain": str(e)}) from e
        if not self.schema_name:
            self.schema_name = _default_schema_name(
                self.nombre,
                self.subdomain,
                self.tenant_code,
            )
        super().save(*args, **kwargs)

    class Meta:
        db_table = "portal_tenant"

    def __str__(self):
        return f"{self.pk} : {self.nombre}"


class TenantDomain(DomainMixin):
    class Meta:
        db_table = "portal_tenant_domain"
        verbose_name = "Tenant domain"
        verbose_name_plural = "Tenant domains"


class TenantManager(models.Manager):
    def get_queryset(self):
        tenant = current_tenant.get()
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
    objects = TenantManager()

    class Meta:
        abstract = True


# ---------------------------------------------------------------------------
# User model and related (AUTH_USER_MODEL)
# ---------------------------------------------------------------------------


class UserManager(BaseUserManager):
    def create_user(self, email, username, password=None, **extra_fields):
        if not email:
            raise ValueError("The email must be set")
        if not username:
            raise ValueError("The username must be set")
        email = self.normalize_email(email)
        user = self.model(email=email, username=username, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, username, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        extra_fields.setdefault("is_active", True)
        if extra_fields.get("is_staff") is not True:
            raise ValueError("Superuser must have is_staff=True.")
        if extra_fields.get("is_superuser") is not True:
            raise ValueError("Superuser must have is_superuser=True.")
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
    avatar = models.ImageField(upload_to="avatars/", default="avatars/default-avatar.png")
    preferences = models.JSONField(default=dict, blank=True)

    groups = models.ManyToManyField(
        "auth.Group",
        verbose_name="groups",
        blank=True,
        related_name="moiouser_set",
        related_query_name="moiouser",
    )
    user_permissions = models.ManyToManyField(
        "auth.Permission",
        verbose_name="user permissions",
        blank=True,
        related_name="moiouser_set",
        related_query_name="moiouser",
    )

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["username"]

    objects = UserManager()

    class Meta:
        db_table = "tenancy_moiouser"

    def __str__(self):
        return self.email

    def get_short_name(self):
        return self.first_name or self.username

    @property
    def name(self):
        return self.first_name or self.username


class UserProfile(models.Model):
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
        db_table = "tenancy_user_profile"
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
        db_table = "tenancy_auth_session"

    def revoke(self, save: bool = True) -> None:
        if not self.revoked_at:
            self.revoked_at = timezone.now()
            if save:
                self.save(update_fields=["revoked_at"])


class UserApiKey(models.Model):
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
        db_table = "tenancy_userapikey"
        verbose_name = "User API Key"
        verbose_name_plural = "User API Keys"
        ordering = ["-created_at"]

    def __str__(self):
        return f"API Key for {self.user.email}"

    @property
    def masked_key(self):
        if not self.key_hash:
            return ""
        return "moio_****...****"

    def generate_key(self):
        chars = string.ascii_letters + string.digits
        random_part = "".join(secrets.choice(chars) for _ in range(32))
        plain_key = f"moio_{random_part}"
        self.key_hash = hashlib.sha256(plain_key.encode()).hexdigest()
        return plain_key

    def verify_key(self, provided_key):
        return self.key_hash == hashlib.sha256(provided_key.encode()).hexdigest()


# ---------------------------------------------------------------------------
# Integration definitions (DB-backed, agent-facing)
# ---------------------------------------------------------------------------

class IntegrationDefinition(models.Model):
    AUTH_CHOICES = [
        ("none", "No authentication"),
        ("bearer", "Bearer token"),
        ("api_key_header", "API key header"),
        ("api_key_query", "API key query"),
        ("basic", "Basic auth"),
        ("oauth2_client_credentials", "OAuth2 client credentials"),
    ]
    AUTH_SCOPE_CHOICES = [
        ("global", "Global credentials"),
        ("tenant", "Tenant credentials"),
        ("user", "User credentials"),
    ]

    key = models.SlugField(max_length=80, unique=True)
    name = models.CharField(max_length=140)
    category = models.CharField(max_length=80, blank=True, default="")
    base_url = models.URLField(blank=True, default="")
    openapi_url = models.URLField(blank=True, default="")
    default_auth_type = models.CharField(max_length=30, choices=AUTH_CHOICES, default="bearer")
    auth_scope = models.CharField(max_length=20, choices=AUTH_SCOPE_CHOICES, default="tenant")
    auth_config_schema = models.JSONField(default=dict, blank=True)
    global_auth_config = models.JSONField(default=dict, blank=True)
    assistant_docs_markdown = models.TextField(blank=True, default="")
    default_headers = models.JSONField(default=dict, blank=True)
    is_active = models.BooleanField(default=True)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "tenancy_integration_definition"
        ordering = ["key"]

    def __str__(self) -> str:
        return self.name or self.key


class TenantIntegration(models.Model):
    tenant = models.ForeignKey(
        Tenant,
        on_delete=models.CASCADE,
        related_name="integration_bindings",
    )
    integration = models.ForeignKey(
        IntegrationDefinition,
        on_delete=models.CASCADE,
        related_name="tenant_bindings",
    )
    is_enabled = models.BooleanField(default=True)
    assistant_docs_override = models.TextField(blank=True, default="")
    notes = models.TextField(blank=True, default="")
    tenant_auth_config = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "tenancy_tenant_integration"
        ordering = ["tenant_id", "integration_id"]
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "integration"],
                name="tenancy_uq_tenant_integration",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.tenant.nombre}:{self.integration.key}"
