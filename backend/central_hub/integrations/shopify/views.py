"""
Shopify Embedded App Views

Handles:
- OAuth install/callback for the Shopify App (embedded in Shopify admin)
- Embed config endpoint used by the React embedded-app page
- Manual sync trigger endpoints
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import time
from urllib.parse import urlencode

from django.http import HttpResponseRedirect
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from central_hub.authentication import CsrfExemptSessionAuthentication, TenantJWTAAuthentication
from central_hub.integrations.models import IntegrationConfig
from central_hub.models import PlatformConfiguration
from security.authentication import ServiceJWTAuthentication

logger = logging.getLogger(__name__)

SHOPIFY_SCOPES = "read_products,read_customers,read_orders"


def _get_portal_config() -> PlatformConfiguration | None:
    return PlatformConfiguration.objects.first()


def _build_redirect_uri(portal_config: PlatformConfiguration) -> str:
    base = (portal_config.my_url or "").rstrip("/")
    return f"{base}/api/v1/integrations/shopify/oauth/callback/"


def _verify_shopify_hmac(params: dict, secret: str) -> bool:
    """Verify the HMAC signature from Shopify OAuth redirect."""
    hmac_value = params.pop("hmac", None)
    if not hmac_value:
        return False
    sorted_params = "&".join(f"{k}={v}" for k, v in sorted(params.items()))
    digest = hmac.new(secret.encode(), sorted_params.encode(), hashlib.sha256).hexdigest()
    return hmac.compare_digest(digest, hmac_value)


class ShopifyIntegrationAPIView(APIView):
    authentication_classes = [
        CsrfExemptSessionAuthentication,
        TenantJWTAAuthentication,
        ServiceJWTAuthentication,
    ]

    def get_tenant(self):
        return getattr(self.request.user, "tenant", None)


# ---------------------------------------------------------------------------
# OAuth – Install (entry point, no auth required)
# ---------------------------------------------------------------------------

@method_decorator(csrf_exempt, name="dispatch")
class ShopifyOAuthInstallView(APIView):
    """
    GET /api/v1/integrations/shopify/oauth/install/?shop=mystore.myshopify.com&host=<base64>

    Redirects the merchant to Shopify's OAuth consent screen.
    Called when the merchant installs or opens the app from the Shopify admin.
    """
    authentication_classes = []
    permission_classes = []

    def get(self, request):
        shop = request.GET.get("shop", "").strip()
        host = request.GET.get("host", "")

        if not shop:
            return Response({"error": "shop parameter is required"}, status=status.HTTP_400_BAD_REQUEST)

        portal_config = _get_portal_config()
        if not portal_config or not portal_config.shopify_client_id:
            return Response(
                {"error": "Shopify app credentials not configured. Set shopify_client_id in PlatformConfiguration."},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        redirect_uri = _build_redirect_uri(portal_config)
        state = f"{int(time.time())}"  # simple nonce (production: store in session)

        params = {
            "client_id": portal_config.shopify_client_id,
            "scope": SHOPIFY_SCOPES,
            "redirect_uri": redirect_uri,
            "state": state,
        }
        if host:
            params["host"] = host

        oauth_url = f"https://{shop}/admin/oauth/authorize?{urlencode(params)}"
        return HttpResponseRedirect(oauth_url)


# ---------------------------------------------------------------------------
# OAuth – Callback
# ---------------------------------------------------------------------------

@method_decorator(csrf_exempt, name="dispatch")
class ShopifyOAuthCallbackView(APIView):
    """
    GET /api/v1/integrations/shopify/oauth/callback/?code=...&shop=...&host=...

    Exchanges the OAuth code for an access token, persists the IntegrationConfig,
    then redirects to the embedded-app frontend page.
    """
    authentication_classes = []
    permission_classes = []

    def get(self, request):
        import requests as http_requests

        params = dict(request.GET)
        # GET params come as lists from Django; flatten
        params = {k: v[0] if isinstance(v, list) else v for k, v in params.items()}

        shop = params.get("shop", "").strip()
        code = params.get("code", "").strip()
        host = params.get("host", "")

        if not shop or not code:
            return Response({"error": "shop and code are required"}, status=status.HTTP_400_BAD_REQUEST)

        portal_config = _get_portal_config()
        if not portal_config or not portal_config.shopify_client_id or not portal_config.shopify_client_secret:
            return Response(
                {"error": "Shopify app credentials not configured"},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        # Verify HMAC (skip 'state' and 'host' which are not part of the signature)
        verify_params = {k: v for k, v in params.items() if k not in ("state", "host")}
        if not _verify_shopify_hmac(verify_params, portal_config.shopify_client_secret):
            logger.warning("Shopify OAuth callback HMAC verification failed for shop=%s", shop)
            return Response({"error": "HMAC verification failed"}, status=status.HTTP_403_FORBIDDEN)

        # Exchange code for access token
        try:
            resp = http_requests.post(
                f"https://{shop}/admin/oauth/access_token",
                json={
                    "client_id": portal_config.shopify_client_id,
                    "client_secret": portal_config.shopify_client_secret,
                    "code": code,
                },
                timeout=15,
            )
            resp.raise_for_status()
            token_data = resp.json()
            access_token = token_data.get("access_token", "")
        except Exception as exc:
            logger.exception("Shopify token exchange failed for shop=%s", shop)
            return Response({"error": f"Token exchange failed: {exc}"}, status=status.HTTP_502_BAD_GATEWAY)

        if not access_token:
            return Response({"error": "No access_token in Shopify response"}, status=status.HTTP_502_BAD_GATEWAY)

        # Persist / update IntegrationConfig for the shop.
        # We use the shop domain as instance_id so multiple shops are supported.
        instance_id = shop.replace(".myshopify.com", "").replace(".", "-")

        # Find the first available tenant (in a real deployment you'd map shop → tenant)
        from tenancy.models import Tenant
        tenant = Tenant.objects.filter(schema_name="public").first() or Tenant.objects.first()

        if tenant:
            config_obj, _ = IntegrationConfig.get_or_create_for_tenant(
                tenant=tenant,
                slug="shopify",
                instance_id=instance_id,
                defaults={
                    "enabled": True,
                    "name": shop,
                    "config": {
                        "store_url": shop,
                        "access_token": access_token,
                        "api_version": "2024-01",
                        "direction": "receive",
                        "receive_products": True,
                        "receive_customers": True,
                        "receive_orders": True,
                        "receive_inventory": True,
                    },
                },
            )
            config_obj.config["access_token"] = access_token
            config_obj.config["store_url"] = shop
            config_obj.enabled = True
            config_obj.save()
            logger.info("Shopify OAuth: saved IntegrationConfig for shop=%s instance_id=%s", shop, instance_id)

        # Redirect to the embedded-app frontend page
        frontend_url = (portal_config.my_url or "").rstrip("/")
        redirect_to = f"{frontend_url}/shopify-embed?shop={shop}&host={host}&instance_id={instance_id}"
        return HttpResponseRedirect(redirect_to)


# ---------------------------------------------------------------------------
# Embed config – supplies shop info to the React page (requires moio auth)
# ---------------------------------------------------------------------------

@method_decorator(csrf_exempt, name="dispatch")
class ShopifyEmbedConfigView(ShopifyIntegrationAPIView):
    """
    GET  /api/v1/integrations/shopify/embed/config/?instance_id=<id>
    PATCH /api/v1/integrations/shopify/embed/config/

    GET  – Returns full Shopify config (sensitive fields masked) + platform URLs.
    PATCH – Saves platform-level settings (app_url, shopify_client_id/secret).
            These live on PlatformConfiguration, not on IntegrationConfig.
    """

    def get(self, request):
        tenant = self.get_tenant()
        if not tenant:
            return Response({"error": "Authentication required"}, status=status.HTTP_401_UNAUTHORIZED)

        instance_id = request.GET.get("instance_id", "default")
        config_obj = IntegrationConfig.objects.filter(
            tenant=tenant, slug="shopify", instance_id=instance_id
        ).first()

        portal_config = _get_portal_config()
        cfg = config_obj.config if config_obj else {}

        def _mask(val: str) -> str:
            if not val:
                return ""
            return "••••••••"

        data = {
            "shopify_client_id": (portal_config.shopify_client_id or "") if portal_config else "",
            "shopify_client_id_set": bool((portal_config.shopify_client_id or "") if portal_config else ""),
            "shopify_client_secret_set": bool((portal_config.shopify_client_secret or "") if portal_config else ""),
            # Public app URL (tunnel / production URL)
            "app_url": (portal_config.my_url or "") if portal_config else "",
            # Derived URLs shown to the user for Shopify app partner setup
            "oauth_callback_url": _build_redirect_uri(portal_config) if portal_config else "",
            "webhook_base_url": (
                f"{(portal_config.my_url or '').rstrip('/')}/api/v1/integrations/shopify/webhook/"
                if portal_config else ""
            ),
            "instance_id": instance_id,
            "configured": config_obj is not None,
            "enabled": config_obj.enabled if config_obj else False,
            # Connection
            "store_url": cfg.get("store_url") or "",
            "access_token": _mask(cfg.get("access_token") or ""),
            "access_token_set": bool(cfg.get("access_token")),
            "api_version": cfg.get("api_version") or "2024-01",
            "webhook_secret": _mask(cfg.get("webhook_secret") or ""),
            "webhook_secret_set": bool(cfg.get("webhook_secret")),
            # Direction
            "direction": cfg.get("direction") or "receive",
            # Receive toggles
            "receive_products": bool(cfg.get("receive_products", True)),
            "receive_customers": bool(cfg.get("receive_customers", True)),
            "receive_orders": bool(cfg.get("receive_orders", True)),
            "receive_inventory": bool(cfg.get("receive_inventory", True)),
            # Send toggles
            "send_inventory_updates": bool(cfg.get("send_inventory_updates", False)),
            "send_order_updates": bool(cfg.get("send_order_updates", False)),
            # Sync metadata
            "last_sync_metadata": (config_obj.metadata or {}) if config_obj else {},
        }
        return Response(data)

    def patch(self, request):
        """Save platform-level Shopify app settings (app_url, client credentials)."""
        tenant = self.get_tenant()
        if not tenant:
            return Response({"error": "Authentication required"}, status=status.HTTP_401_UNAUTHORIZED)

        portal_config = _get_portal_config()
        if not portal_config:
            return Response({"error": "Platform configuration not found"}, status=status.HTTP_404_NOT_FOUND)

        data = request.data
        changed = False

        app_url = data.get("app_url", "").strip()
        if app_url and app_url != portal_config.my_url:
            portal_config.my_url = app_url
            changed = True

        shopify_client_id = data.get("shopify_client_id", "").strip()
        if shopify_client_id:
            portal_config.shopify_client_id = shopify_client_id
            changed = True

        shopify_client_secret = data.get("shopify_client_secret", "").strip()
        if shopify_client_secret:
            portal_config.shopify_client_secret = shopify_client_secret
            changed = True

        if changed:
            portal_config.save(update_fields=["my_url", "shopify_client_id", "shopify_client_secret"])
            # Invalidate the DynamicCsrfMiddleware cache so the new URL is trusted immediately
            try:
                from moio_platform.csrf_middleware import DynamicCsrfMiddleware  # noqa: PLC0415
                DynamicCsrfMiddleware._cache_ts = 0.0
            except Exception:
                pass

        return Response({"ok": True, "app_url": portal_config.my_url})


# ---------------------------------------------------------------------------
# Embed sync trigger – kick off async sync tasks
# ---------------------------------------------------------------------------

@method_decorator(csrf_exempt, name="dispatch")
class ShopifyEmbedSyncView(ShopifyIntegrationAPIView):
    """
    POST /api/v1/integrations/shopify/embed/sync/

    Body: { "instance_id": "...", "sync_type": "all" | "products" | "customers" | "orders" }

    Queues a Celery sync task for the requesting tenant.
    """

    def post(self, request):
        tenant = self.get_tenant()
        if not tenant:
            return Response({"error": "Authentication required"}, status=status.HTTP_401_UNAUTHORIZED)

        instance_id = request.data.get("instance_id", "default")
        sync_type = request.data.get("sync_type", "all")

        config_obj = IntegrationConfig.objects.filter(
            tenant=tenant, slug="shopify", instance_id=instance_id
        ).first()
        if not config_obj:
            return Response(
                {"error": f"Shopify integration not configured for instance '{instance_id}'"},
                status=status.HTTP_404_NOT_FOUND,
            )

        try:
            from central_hub.integrations.shopify import tasks as shopify_tasks

            if sync_type == "products":
                task = shopify_tasks.sync_shopify_products.delay(
                    tenant_id=str(tenant.pk), instance_id=instance_id
                )
            elif sync_type == "customers":
                task = shopify_tasks.sync_shopify_customers.delay(
                    tenant_id=str(tenant.pk), instance_id=instance_id
                )
            elif sync_type == "orders":
                task = shopify_tasks.sync_shopify_orders.delay(
                    tenant_id=str(tenant.pk), instance_id=instance_id
                )
            else:
                task = shopify_tasks.sync_all_shopify_data.delay(
                    tenant_id=str(tenant.pk), instance_id=instance_id
                )

            return Response({"status": "queued", "task_id": task.id, "sync_type": sync_type})
        except Exception as exc:
            logger.exception("Failed to queue Shopify sync task")
            return Response({"error": str(exc)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
