"""
Shopify Integration Adapter (Integrations Hub contract).

Official platform wrapper for Shopify. Encapsulates OAuth, webhooks, sync.
Phase 1: implements adapter interface and delegates to existing views/webhook_receiver.
Phase 2: will own shop-domain-driven binding resolution and sync task dispatch.
"""

from __future__ import annotations

import logging
from typing import Any

from django.http import HttpRequest, HttpResponse

from central_hub.integrations.contract import (
    IntegrationAdapter,
    IntegrationBindingStatus,
)

logger = logging.getLogger(__name__)


class ShopifyAdapter(IntegrationAdapter):
    slug = "shopify"

    def connect(self, tenant_id: int, instance_id: str, credentials: dict[str, Any]) -> dict[str, Any]:
        """OAuth flow is handled by ShopifyOAuthCallbackView; link by ShopifyEmbedLinkView."""
        return {
            "instance_id": instance_id,
            "status": IntegrationBindingStatus.CONNECTED.value,
            "message": "Use OAuth install and embed/link endpoints to connect.",
        }

    def disconnect(self, tenant_id: int, instance_id: str) -> None:
        """Clear connection for this binding; unlink shop or disable config."""
        from central_hub.integrations.models import (
            IntegrationConfig,
            IntegrationBindingStatus,
            ShopifyShopLink,
            ShopifyShopLinkStatus,
        )
        from django.utils import timezone

        config = IntegrationConfig.objects.filter(
            tenant_id=tenant_id,
            slug=self.slug,
            instance_id=instance_id,
        ).first()
        if config:
            config.enabled = False
            config.status = IntegrationBindingStatus.UNINSTALLED
            config.config.pop("access_token", None)
            config.save(update_fields=["enabled", "status", "config", "updated_at"])
        # If instance_id is shop-derived, unlink ShopifyShopLink
        shop_domain = _instance_id_to_shop_domain(instance_id)
        if shop_domain:
            ShopifyShopLink.objects.filter(
                shop_domain=shop_domain,
                tenant_id=tenant_id,
                status=ShopifyShopLinkStatus.LINKED,
            ).update(
                status=ShopifyShopLinkStatus.UNLINKED,
                unlinked_at=timezone.now(),
            )

    def validate(self, tenant_id: int, instance_id: str, config: dict[str, Any] | None) -> tuple[bool, str]:
        """Validate Shopify credentials (store_url + access_token)."""
        from central_hub.integrations.models import IntegrationConfig
        from central_hub.integrations.shopify.shopify_api import ShopifyAPIClient

        if config is None:
            cfg = IntegrationConfig.objects.filter(
                tenant_id=tenant_id,
                slug=self.slug,
                instance_id=instance_id,
            ).first()
            config = (cfg.config if cfg else {}) or {}

        store_url = (config.get("store_url") or "").strip()
        access_token = (config.get("access_token") or "").strip()
        api_version = (config.get("api_version") or "2024-01").strip()
        if not store_url or not access_token:
            return False, "Store URL and access token are required"
        try:
            client = ShopifyAPIClient(store_url=store_url, access_token=access_token, api_version=api_version)
            ok = client.test_connection()
            return (ok, "Connection OK") if ok else (False, "Connection test failed")
        except Exception as e:
            return False, str(e)

    def handle_webhook(
        self,
        request: HttpRequest,
        topic: str,
        payload: dict[str, Any],
        headers: dict[str, str],
    ) -> HttpResponse:
        """Delegate to existing webhook receiver (HMAC + dispatch)."""
        from central_hub.integrations.shopify.webhook_receiver import shopify_webhook_receiver
        return shopify_webhook_receiver(request)

    def health(self, tenant_id: int, instance_id: str) -> dict[str, Any]:
        """Return last_connection_ok and last_connection_at from config metadata."""
        from central_hub.integrations.models import IntegrationConfig
        cfg = IntegrationConfig.objects.filter(
            tenant_id=tenant_id,
            slug=self.slug,
            instance_id=instance_id,
        ).first()
        if not cfg:
            return {"status": "not_found"}
        meta = cfg.metadata or {}
        return {
            "status": cfg.status,
            "last_connection_ok": meta.get("last_connection_ok"),
            "last_connection_at": meta.get("last_connection_at"),
        }

    def public_summary(self, tenant_id: int, instance_id: str) -> dict[str, Any]:
        """Safe summary for UI (no secrets)."""
        from central_hub.integrations.models import IntegrationConfig
        cfg = IntegrationConfig.objects.filter(
            tenant_id=tenant_id,
            slug=self.slug,
            instance_id=instance_id,
        ).first()
        if not cfg:
            return {
                "slug": self.slug,
                "instance_id": instance_id,
                "status": IntegrationBindingStatus.PENDING_LINK.value,
            }
        return {
            "slug": self.slug,
            "instance_id": instance_id,
            "name": cfg.name or instance_id,
            "status": cfg.status,
            "enabled": cfg.enabled,
        }


def _instance_id_to_shop_domain(instance_id: str) -> str:
    """Convert instance_id (store subdomain) to shop_domain (e.g. moioplatform -> moioplatform.myshopify.com)."""
    if not instance_id or instance_id == "default":
        return ""
    return f"{instance_id}.myshopify.com"
