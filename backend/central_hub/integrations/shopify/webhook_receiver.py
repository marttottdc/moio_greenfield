"""
Shopify webhook HTTP receiver: single endpoint with HMAC verification and topic dispatch.

Handles:
- HMAC verification (X-Shopify-Hmac-Sha256)
- app/uninstalled: mark installation uninstalled, unlink shop
- customers/data_request, customers/redact, shop/redact: GDPR compliance (ack with 200)
- products/*, orders/*: optional dispatch to existing async handlers
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
from datetime import timedelta

from django.http import HttpResponse, JsonResponse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from central_hub.integrations.models import (
    IntegrationConfig,
    IntegrationBindingStatus,
    ShopifyShopInstallation,
    ShopifyShopLink,
    ShopifyShopLinkStatus,
)
from central_hub.models import PlatformConfiguration

logger = logging.getLogger(__name__)

# If we received an install (OAuth) this many seconds ago, treat a later uninstall webhook as stale
# (Shopify sent uninstall before we got the reinstall; don't wipe the new token)
UNINSTALL_STALE_AFTER_INSTALL_SECONDS = 300  # 5 minutes

SHOPIFY_HMAC_HEADER = "HTTP_X_SHOPIFY_HMAC_SHA256"
SHOPIFY_TOPIC_HEADER = "HTTP_X_SHOPIFY_TOPIC"
SHOPIFY_SHOP_HEADER = "HTTP_X_SHOPIFY_SHOP_DOMAIN"


def _get_portal_config() -> PlatformConfiguration | None:
    """Use public-request helper so unauthenticated webhook requests always see the row."""
    from central_hub.config import get_platform_configuration_for_public_request
    return get_platform_configuration_for_public_request()


def mark_shopify_shop_uninstalled(shop_domain: str) -> None:
    """
    Clear our state for a Shopify shop (installation token, configs, links).
    Call from app/uninstalled webhook and when sync gets 401 (token revoked).

    IntegrationConfig can live in tenant schema (get_for_tenant tries tenant first),
    so we update config inside each linked tenant's schema, then public.
    """
    if not shop_domain or ".myshopify.com" not in shop_domain:
        return
    instance_id = shop_domain.replace(".myshopify.com", "").strip()

    # Update IntegrationConfig in each linked tenant's schema (config is often written there)
    links = list(
        ShopifyShopLink.objects.filter(shop_domain=shop_domain).select_related("tenant")
    )
    from tenancy.tenant_support import schema_context
    for link in links:
        schema_name = getattr(link.tenant, "schema_name", None)
        if schema_name:
            try:
                with schema_context(schema_name):
                    for cfg in IntegrationConfig.objects.filter(
                        tenant_id=link.tenant_id, slug="shopify", instance_id=instance_id
                    ):
                        cfg.enabled = False
                        cfg.status = IntegrationBindingStatus.UNINSTALLED
                        cfg.config.pop("access_token", None)
                        cfg.save(update_fields=["enabled", "status", "config", "updated_at"])
                        logger.info(
                            "mark_shopify_shop_uninstalled: disabled config in tenant schema %s for shop=%s",
                            schema_name, shop_domain,
                        )
            except Exception as e:
                logger.warning(
                    "mark_shopify_shop_uninstalled: failed to update config in schema %s: %s",
                    schema_name, e,
                )
    # Also update any config in public schema (shared table with tenant_id)
    try:
        if schema_context is not None:
            with schema_context("public"):
                for cfg in IntegrationConfig._base_manager.filter(
                    slug="shopify", instance_id=instance_id
                ):
                    cfg.enabled = False
                    cfg.status = IntegrationBindingStatus.UNINSTALLED
                    cfg.config.pop("access_token", None)
                    cfg.save(update_fields=["enabled", "status", "config", "updated_at"])
                    logger.info(
                        "mark_shopify_shop_uninstalled: disabled config in public for shop=%s",
                        shop_domain,
                    )
        else:
            for cfg in IntegrationConfig._base_manager.filter(
                slug="shopify", instance_id=instance_id
            ):
                cfg.enabled = False
                cfg.status = IntegrationBindingStatus.UNINSTALLED
                cfg.config.pop("access_token", None)
                cfg.save(update_fields=["enabled", "status", "config", "updated_at"])
                logger.info(
                    "mark_shopify_shop_uninstalled: disabled config (no schema_context) for shop=%s",
                    shop_domain,
                )
    except Exception as e:
        logger.warning("mark_shopify_shop_uninstalled: failed to update config in public: %s", e)

    installation = ShopifyShopInstallation.objects.filter(shop_domain=shop_domain).first()
    if installation:
        installation.uninstalled_at = timezone.now()
        installation.offline_access_token = ""
        installation.refresh_token = ""
        installation.save(update_fields=["uninstalled_at", "offline_access_token", "refresh_token"])
        logger.info("mark_shopify_shop_uninstalled: cleared installation token for shop=%s", shop_domain)
    ShopifyShopLink.objects.filter(shop_domain=shop_domain).update(
        status=ShopifyShopLinkStatus.UNLINKED,
        unlinked_at=timezone.now(),
    )
    logger.info("mark_shopify_shop_uninstalled: done for shop=%s", shop_domain)


def _verify_shopify_webhook_hmac(body: bytes, signature: str, secret: str) -> bool:
    """Verify Shopify webhook HMAC. Signature is base64-encoded HMAC-SHA256(body, secret)."""
    if not signature or not secret:
        return False
    try:
        computed = hmac.new(secret.encode(), body, hashlib.sha256).digest()
        expected_b64 = base64.b64encode(computed).decode("ascii")
        return hmac.compare_digest(expected_b64, signature)
    except Exception:
        return False


@require_http_methods(["POST"])
@csrf_exempt
def shopify_webhook_receiver(request):
    """
    POST /api/v1/integrations/shopify/webhook/

    Verifies X-Shopify-Hmac-Sha256, then dispatches by X-Shopify-Topic.
    """
    body = request.body
    hmac_header = request.META.get(SHOPIFY_HMAC_HEADER, "")
    topic = request.META.get(SHOPIFY_TOPIC_HEADER, "")
    shop_domain = request.META.get(SHOPIFY_SHOP_HEADER, "")

    if not topic or not shop_domain:
        return JsonResponse({"error": "Missing Shopify webhook headers"}, status=400)

    portal_config = _get_portal_config()
    if not portal_config or not portal_config.shopify_client_secret:
        logger.warning("Shopify webhook: no client secret configured")
        return JsonResponse({"error": "Webhook not configured"}, status=503)

    if not _verify_shopify_webhook_hmac(body, hmac_header, portal_config.shopify_client_secret):
        logger.warning("Shopify webhook HMAC verification failed for shop=%s topic=%s", shop_domain, topic)
        return JsonResponse({"error": "Invalid signature"}, status=401)

    logger.info(
        "Shopify webhook received and verified: topic=%s shop=%s (handler=shopify_webhook_receiver)",
        topic,
        shop_domain,
    )

    try:
        payload = json.loads(body.decode("utf-8")) if body else {}
    except Exception:
        payload = {}

    # GDPR / lifecycle compliance: respond 200 quickly, then process
    if topic == "app/uninstalled":
        try:
            logger.info("Shopify app/uninstalled: step 1 – received for shop=%s", shop_domain)
            # If Shopify is slow and we already processed a reinstall, don't wipe the new token
            installation = ShopifyShopInstallation.objects.filter(shop_domain=shop_domain).first()
            if installation and getattr(installation, "last_seen_at", None):
                cutoff = timezone.now() - timedelta(seconds=UNINSTALL_STALE_AFTER_INSTALL_SECONDS)
                if installation.last_seen_at >= cutoff:
                    logger.info(
                        "Shopify app/uninstalled: skipping for shop=%s (install seen %s ago; treating as stale uninstall)",
                        shop_domain,
                        timezone.now() - installation.last_seen_at,
                    )
                else:
                    mark_shopify_shop_uninstalled(shop_domain)
            else:
                mark_shopify_shop_uninstalled(shop_domain)
        except Exception as e:
            logger.exception("Shopify app/uninstalled handler failed: %s", e)
        return HttpResponse(status=200)

    if topic == "customers/data_request":
        # Acknowledge; actual data export can be async or documented
        logger.info("Shopify customers/data_request for shop=%s", shop_domain)
        return HttpResponse(status=200)

    if topic == "customers/redact":
        # Acknowledge; actual redaction can be async
        logger.info("Shopify customers/redact for shop=%s", shop_domain)
        return HttpResponse(status=200)

    if topic == "shop/redact":
        # Acknowledge; delete shop data as per GDPR
        logger.info("Shopify shop/redact for shop=%s", shop_domain)
        return HttpResponse(status=200)

    # Optional: queue product/order webhooks for existing handlers
    if topic in ("products/create", "products/update", "products/delete",
                 "orders/create", "orders/update", "orders/cancelled", "orders/fulfilled",
                 "customers/create", "customers/update"):
        try:
            from central_hub.integrations.shopify.tasks import process_shopify_webhook
            link = ShopifyShopLink.objects.filter(shop_domain=shop_domain, status=ShopifyShopLinkStatus.LINKED).select_related("tenant").first()
            if link:
                tenant_code = str(getattr(link.tenant, "tenant_code", "") or "")
                if tenant_code and tenant_code != "None":
                    process_shopify_webhook.delay(
                        payload=payload,
                        headers={"X-Shopify-Topic": topic, "X-Shopify-Shop-Domain": shop_domain},
                        tenant_code=tenant_code,
                        topic=topic,
                    )
        except Exception as e:
            logger.exception("Shopify webhook queue failed: %s", e)
        return HttpResponse(status=200)

    return HttpResponse(status=200)
