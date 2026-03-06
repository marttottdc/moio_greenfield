"""
IntegrationConfig Model

A flexible, multi-instance integration configuration model that replaces
the flat-field approach in TenantConfiguration.

Features:
- Multi-instance support: Multiple configs of same type per tenant (e.g., 2 WhatsApp numbers)
- JSON config storage: No migrations needed for new integration fields
- Schema validation: Per-integration validation via registry
- Write-through sync: Changes to TenantConfiguration auto-sync here
"""

from __future__ import annotations

import uuid
from typing import Any

from django.db import models
from django.utils import timezone

from portal.models import Tenant, TenantScopedModel


class IntegrationConfig(TenantScopedModel):
    """
    Stores integration configuration for a tenant.
    
    Supports multiple instances of the same integration type per tenant.
    For example, a tenant could have two WhatsApp Business accounts:
    - IntegrationConfig(slug="whatsapp", instance_id="sales", ...)
    - IntegrationConfig(slug="whatsapp", instance_id="support", ...)
    """
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(
        Tenant,
        on_delete=models.CASCADE,
        related_name="integration_configs"
    )
    slug = models.CharField(
        max_length=50,
        db_index=True,
        help_text="Integration type identifier (e.g., 'whatsapp', 'openai')"
    )
    instance_id = models.CharField(
        max_length=50,
        default="default",
        help_text="Instance identifier for multi-instance integrations (e.g., 'sales', 'support')"
    )
    name = models.CharField(
        max_length=100,
        blank=True,
        default="",
        help_text="Human-readable name for this integration instance"
    )
    enabled = models.BooleanField(
        default=False,
        help_text="Whether this integration is active"
    )
    config = models.JSONField(
        default=dict,
        help_text="Integration-specific configuration data"
    )
    metadata = models.JSONField(
        default=dict,
        blank=True,
        help_text="Additional metadata (last_sync, error_count, etc.)"
    )
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = "integration_config"
        verbose_name = "Integration Configuration"
        verbose_name_plural = "Integration Configurations"
        unique_together = ("tenant", "slug", "instance_id")
        ordering = ["slug", "instance_id"]
        indexes = [
            models.Index(fields=["tenant", "slug"]),
            models.Index(fields=["slug", "enabled"]),
        ]
    
    def __str__(self) -> str:
        if self.instance_id == "default":
            return f"{self.tenant} - {self.slug}"
        return f"{self.tenant} - {self.slug}:{self.instance_id}"
    
    def get_config_value(self, key: str, default: Any = None) -> Any:
        """Get a specific config value with optional default."""
        return self.config.get(key, default)
    
    def set_config_value(self, key: str, value: Any) -> None:
        """Set a specific config value."""
        self.config[key] = value
    
    def is_configured(self) -> bool:
        """Check if the integration has required configuration."""
        from portal.integrations.registry import get_required_fields
        required = get_required_fields(self.slug)
        return all(self.config.get(field) for field in required)
    
    def validate_config(self) -> list[str]:
        """Validate config against the registered schema. Returns list of errors."""
        from portal.integrations.registry import validate_integration_config
        return validate_integration_config(self.slug, self.config)
    
    @classmethod
    def get_for_tenant(
        cls,
        tenant: Tenant,
        slug: str,
        instance_id: str = "default"
    ) -> "IntegrationConfig | None":
        """Get integration config for a tenant, or None if not found."""
        return cls.objects.filter(
            tenant=tenant,
            slug=slug,
            instance_id=instance_id
        ).first()
    
    @classmethod
    def get_or_create_for_tenant(
        cls,
        tenant: Tenant,
        slug: str,
        instance_id: str = "default",
        defaults: dict | None = None
    ) -> tuple["IntegrationConfig", bool]:
        """Get or create integration config for a tenant."""
        return cls.objects.get_or_create(
            tenant=tenant,
            slug=slug,
            instance_id=instance_id,
            defaults=defaults or {}
        )
    
    @classmethod
    def get_enabled_for_tenant(cls, tenant: Tenant, slug: str) -> models.QuerySet:
        """Get all enabled integration configs of a type for a tenant."""
        return cls.objects.filter(tenant=tenant, slug=slug, enabled=True)

# =============================================================================
# Shopify embedded admin support (shop-scoped models)
# =============================================================================


class ShopifyShopInstallation(models.Model):
    """
    One record per installed Shopify shop.

    Stores the *offline* Admin API token used for Shopify Admin GraphQL mutations.
    """

    shop_domain = models.CharField(max_length=255, unique=True, db_index=True)

    # NOTE: Must be encrypted at rest in production. Stored as opaque string for now.
    offline_access_token = models.TextField(blank=True, default="")

    scopes = models.TextField(blank=True, default="")
    api_version = models.CharField(max_length=20, blank=True, default="2025-10")

    installed_at = models.DateTimeField(null=True, blank=True)
    uninstalled_at = models.DateTimeField(null=True, blank=True)

    last_seen_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "shopify_shop_installation"
        indexes = [
            models.Index(fields=["shop_domain"]),
            models.Index(fields=["uninstalled_at"]),
        ]

    def __str__(self) -> str:
        return self.shop_domain


class ShopifyShopLinkStatus(models.TextChoices):
    LINKED = "linked", "Linked"
    UNLINKED = "unlinked", "Unlinked"


class ShopifyShopLink(models.Model):
    """
    Reversible link between a Shopify shop and a tenant.

    Authorization rule is enforced at the API layer: only a tenant_admin can
    link/unlink a shop.
    """

    shop_domain = models.CharField(max_length=255, unique=True, db_index=True)
    installation = models.ForeignKey(
        ShopifyShopInstallation,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="links",
    )

    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="shopify_shop_links")
    status = models.CharField(
        max_length=16,
        choices=ShopifyShopLinkStatus.choices,
        default=ShopifyShopLinkStatus.LINKED,
    )

    linked_at = models.DateTimeField(default=timezone.now)
    linked_by_email = models.EmailField(blank=True, default="")

    unlinked_at = models.DateTimeField(null=True, blank=True)
    unlinked_by_email = models.EmailField(blank=True, default="")
    unlink_reason = models.CharField(max_length=255, blank=True, default="")

    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "shopify_shop_link"
        indexes = [
            models.Index(fields=["shop_domain", "status"]),
            models.Index(fields=["tenant", "status"]),
        ]

    def __str__(self) -> str:
        return f"{self.shop_domain} -> {self.tenant_id} ({self.status})"


class ShopifyWebhookSubscription(models.Model):
    """
    Stores Shopify webhook subscription IDs per shop/topic so we can reconcile.
    """

    shop_domain = models.CharField(max_length=255, db_index=True)
    topic = models.CharField(max_length=64, db_index=True)

    subscription_id = models.CharField(max_length=255, blank=True, default="")
    callback_url = models.URLField(blank=True, default="")

    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "shopify_webhook_subscription"
        unique_together = ("shop_domain", "topic")
        indexes = [
            models.Index(fields=["shop_domain", "topic"]),
        ]

    def __str__(self) -> str:
        return f"{self.shop_domain} {self.topic}"

