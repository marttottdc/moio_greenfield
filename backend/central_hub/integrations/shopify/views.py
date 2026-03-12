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
import re
import secrets
from urllib.parse import urlencode

from django.contrib.auth.models import Group
from django.db import transaction
from django.http import HttpResponseRedirect
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.utils.text import slugify
from django.views.decorators.csrf import csrf_exempt
from rest_framework import status
from rest_framework.exceptions import AuthenticationFailed
from rest_framework.response import Response
from rest_framework.views import APIView

from central_hub.authentication import CsrfExemptSessionAuthentication, TenantJWTAAuthentication
from central_hub.integrations.shopify.auth import (
    ShopifySessionTokenAuthentication,
    decode_shopify_session_token,
    get_shop_domain_from_payload,
)
from central_hub.integrations.models import (
    IntegrationConfig,
    IntegrationBindingStatus,
    ShopifyOAuthState,
    ShopifyShopInstallation,
    ShopifyShopLink,
    ShopifyShopLinkStatus,
)
from central_hub.models import PlatformConfiguration
from central_hub.rbac import user_has_role
from security.authentication import ServiceJWTAuthentication
from tenancy.models import Tenant, UserProfile

logger = logging.getLogger(__name__)

# Requested at OAuth install. Must match Admin API scopes we use (see https://shopify.dev/docs/api/usage/access-scopes)
# read_products → Product, ProductVariant; read_customers → Customer; read_orders → Order; read_inventory → InventoryLevel, InventoryItem
SHOPIFY_SCOPES = "read_products,read_customers,read_orders,read_inventory"
SHOPIFY_API_VERSION = "2024-01"
OAUTH_STATE_TTL_SECONDS = 600  # 10 minutes

# Frontend path for the embedded app (shared with redirects and docs).
# Must match frontend SHOPIFY_APP_PATH in frontend/client/src/constants/shopify.ts.
SHOPIFY_APP_PATH = "/apps/shopify/app"

# Shopify shop domain must be *.myshopify.com
_SHOP_DOMAIN_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9-]*\.myshopify\.com$")
_CHAT_WIDGET_POSITIONS = {"bottom-right", "bottom-left", "top-right", "top-left"}


def _int_in_range(value, default: int, minimum: int, maximum: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return max(minimum, min(maximum, parsed))


def _get_portal_config() -> PlatformConfiguration | None:
    return PlatformConfiguration.objects.first()


SYNC_INTERVAL_CHOICES = {30, 60, 480, 1440}  # minutes


def _reconcile_periodic_sync(config_obj) -> None:
    """
    Create, update or delete the django-celery-beat PeriodicTask that runs
    periodic_shopify_sync for this integration, based on the sync_interval config value.

    sync_interval is stored as minutes: 30, 60, 480, 1440. 0 or missing = webhooks only (no periodic).
    """
    from moio_platform.lib.task_programmer import TaskProgrammer

    cfg = config_obj.config or {}
    interval_minutes = int(cfg.get("sync_interval") or 0)
    tenant_id = config_obj.tenant_id
    instance_id = config_obj.instance_id or "default"

    tp = TaskProgrammer(tenant=str(tenant_id), prefix="shopify")
    task_name = "central_hub.integrations.shopify.tasks.sync_all_shopify_data"
    schedule_name = f"shopify:{tenant_id}:{instance_id}:periodic_sync"

    should_schedule = (
        config_obj.enabled
        and cfg.get("direction") == "receive"
        and interval_minutes in SYNC_INTERVAL_CHOICES
    )

    if should_schedule:
        if interval_minutes < 60:
            tp.interval(
                task_name,
                every=interval_minutes,
                period="minutes",
                kwargs={"tenant_id": tenant_id, "instance_id": instance_id},
                queue=settings.MEDIUM_PRIORITY_Q,
                name=schedule_name,
                enabled=True,
            )
        else:
            tp.interval(
                task_name,
                every=interval_minutes // 60,
                period="hours",
                kwargs={"tenant_id": tenant_id, "instance_id": instance_id},
                queue=settings.MEDIUM_PRIORITY_Q,
                name=schedule_name,
                enabled=True,
            )
        logger.info("Scheduled periodic sync every %d min for tenant=%s instance=%s", interval_minutes, tenant_id, instance_id)
    else:
        tp.delete(schedule_name)
        logger.info("Removed periodic sync schedule for tenant=%s instance=%s", tenant_id, instance_id)


def _get_webhook_subscriptions_summary(shop_domain: str) -> list[dict]:
    """Return a compact list of active webhook subscriptions for a shop."""
    if not shop_domain:
        return []
    from central_hub.integrations.models import ShopifyWebhookSubscription

    return [
        {"topic": sub.topic, "active": bool(sub.subscription_id)}
        for sub in ShopifyWebhookSubscription.objects.filter(shop_domain=shop_domain)
    ]


def _get_chat_widget_config_for_embed(cfg: dict) -> dict:
    """Extract chat_widget settings for the embed config response (no secrets)."""
    cw = cfg.get("chat_widget") or {}
    if not isinstance(cw, dict):
        return {}
    position = str(cw.get("position", "")).strip() or "bottom-right"
    if position not in _CHAT_WIDGET_POSITIONS:
        position = "bottom-right"
    return {
        "enabled": bool(cw.get("enabled")),
        "title": str(cw.get("title", "")).strip() or "Chat",
        "bubble_icon": str(cw.get("bubble_icon", "")).strip() or "💬",
        "greeting": str(cw.get("greeting", "")).strip() or "Hello! How can we help?",
        "primary_color": str(cw.get("primary_color", "")).strip() or "#000000",
        "position": position,
        "offset_x": _int_in_range(cw.get("offset_x"), default=20, minimum=0, maximum=64),
        "offset_y": _int_in_range(cw.get("offset_y"), default=20, minimum=0, maximum=96),
        "bubble_size": _int_in_range(cw.get("bubble_size"), default=56, minimum=44, maximum=72),
        "window_width": _int_in_range(cw.get("window_width"), default=360, minimum=280, maximum=520),
        "window_height": _int_in_range(cw.get("window_height"), default=480, minimum=320, maximum=760),
        "allowed_templates": cw.get("allowed_templates") if isinstance(cw.get("allowed_templates"), list) else None,
    }


def _build_redirect_uri(portal_config: PlatformConfiguration) -> str:
    base = (portal_config.my_url or "").rstrip("/")
    return f"{base}/api/v1/integrations/shopify/oauth/callback/"


def _shopify_embed_app_url(portal_config: PlatformConfiguration) -> str:
    """Full URL of the Shopify embedded app page (for OAuth redirect target)."""
    base = (portal_config.my_url or "").rstrip("/")
    return f"{base}{SHOPIFY_APP_PATH}"


def _validate_shop_domain(shop: str) -> bool:
    """Validate shop parameter is a valid myshopify.com domain."""
    return bool(shop and _SHOP_DOMAIN_RE.match(shop.strip()))


def _instance_id_for_shop(shop: str) -> str:
    """Shop subdomain as instance_id (e.g. moioplatform.myshopify.com -> moioplatform)."""
    return shop.replace(".myshopify.com", "").strip()


def _resolve_embed_instance_id(request, requested_instance_id: str | None = None) -> str:
    requested = str(requested_instance_id or "").strip()
    shop_domain = str(getattr(request, "shopify_shop_domain", "") or "").strip()
    derived = _instance_id_for_shop(shop_domain) if shop_domain else ""

    # For the embedded app, prefer the shop-derived instance when we have it.
    # This avoids stale "default" configs shadowing the real shop-specific config.
    if derived:
        if not requested or requested == "default" or requested != derived:
            return derived
    return requested or "default"


def ensure_shopify_config_persisted_from_link(tenant: Tenant, instance_id: str) -> IntegrationConfig | None:
    """
    If there is a LINKED ShopifyShopLink and a valid installation for this instance_id,
    write the full config (store_url, access_token, toggles) into IntegrationConfig.
    Call from GET (generic or embed) when stored config is empty so we persist from link/installation.
    """
    from central_hub.integrations.shopify.service import _instance_id_to_shop_domain

    shop_domain = _instance_id_to_shop_domain(instance_id)
    if not shop_domain:
        return None
    link = (
        ShopifyShopLink.objects.filter(
            shop_domain=shop_domain,
            tenant=tenant,
            status=ShopifyShopLinkStatus.LINKED,
        )
        .select_related("installation")
        .first()
    )
    if not link or not getattr(link, "installation", None):
        return None
    installation = link.installation
    if getattr(installation, "uninstalled_at", None) or not (installation.offline_access_token or "").strip():
        return None
    return _ensure_shopify_integration_config(tenant, shop_domain, installation)


def _ensure_shopify_integration_config(
    tenant: Tenant,
    shop: str,
    installation: ShopifyShopInstallation,
) -> IntegrationConfig:
    instance_id = _instance_id_for_shop(shop)
    api_version = (installation.api_version or SHOPIFY_API_VERSION).strip() or SHOPIFY_API_VERSION
    access_token = (installation.offline_access_token or "").strip()

    config_obj, _ = IntegrationConfig.get_or_create_for_tenant(
        tenant=tenant,
        slug="shopify",
        instance_id=instance_id,
        defaults={
            "enabled": True,
            "status": IntegrationBindingStatus.CONNECTED,
            "name": shop,
            "config": {
                "store_url": shop,
                "access_token": access_token,
                "api_version": api_version,
                "direction": "receive",
                "receive_products": True,
                "receive_customers": True,
                "receive_orders": True,
                "receive_inventory": True,
            },
        },
    )
    config_obj.name = shop
    config_obj.enabled = True
    config_obj.status = IntegrationBindingStatus.CONNECTED
    config_obj.config["store_url"] = shop
    if access_token:
        config_obj.config["access_token"] = access_token
    config_obj.config["api_version"] = api_version
    config_obj.save()
    return config_obj


def _build_unique_subdomain(seed: str) -> str:
    base = slugify(seed or "shopify").strip("-") or "shopify"
    base = re.sub(r"[^a-z0-9-]", "-", base.lower()).strip("-") or "shopify"
    base = base[:48].strip("-") or "shopify"
    candidate = base
    suffix = 2
    while Tenant.objects.filter(subdomain=candidate).exists():
        numeric_suffix = f"-{suffix}"
        trimmed = base[: max(1, 48 - len(numeric_suffix))].rstrip("-") or "shopify"
        candidate = f"{trimmed}{numeric_suffix}"
        suffix += 1
    return candidate


def _ensure_user_has_tenant(user, shop: str) -> tuple[Tenant, bool]:
    tenant = getattr(user, "tenant", None)
    schema_name = str(getattr(tenant, "schema_name", "") or "").strip().lower()
    if tenant is not None and schema_name and schema_name != "public":
        return tenant, False

    shop_name = shop.replace(".myshopify.com", "").replace("-", " ").strip() or "Shopify Store"
    tenant = Tenant.objects.create(
        nombre=shop_name.title(),
        domain="moio.local",
        subdomain=_build_unique_subdomain(shop_name),
        plan=Tenant.Plan.FREE,
        enabled=True,
    )
    user.tenant = tenant
    user.save(update_fields=["tenant"])

    group, _ = Group.objects.get_or_create(name="tenant_admin")
    user.groups.add(group)
    UserProfile.objects.get_or_create(
        user=user,
        defaults={
            "display_name": getattr(user, "first_name", "").strip() or getattr(user, "username", "") or getattr(user, "email", ""),
            "locale": "en",
            "timezone": "UTC",
            "onboarding_state": "pending",
            "default_landing": "/dashboard",
        },
    )
    logger.info("Shopify onboarding: auto-provisioned tenant=%s for user=%s", tenant.schema_name, getattr(user, "email", ""))
    return tenant, True


def _serialize_shopify_merchant_profile(shop_info: dict) -> dict:
    return {
        "id": shop_info.get("id"),
        "name": shop_info.get("name") or "",
        "email": shop_info.get("email") or "",
        "shop_owner": shop_info.get("shop_owner") or "",
        "myshopify_domain": shop_info.get("myshopify_domain") or "",
        "domain": shop_info.get("domain") or "",
        "primary_locale": shop_info.get("primary_locale") or "",
        "customer_email": shop_info.get("customer_email") or "",
        "phone": shop_info.get("phone") or "",
        "plan_name": shop_info.get("plan_name") or "",
        "currency": shop_info.get("currency") or "",
        "iana_timezone": shop_info.get("iana_timezone") or "",
        "timezone": shop_info.get("timezone") or "",
        "country_name": shop_info.get("country_name") or "",
        "country_code": shop_info.get("country_code") or "",
        "province": shop_info.get("province") or "",
        "city": shop_info.get("city") or "",
        "zip": shop_info.get("zip") or "",
        "address1": shop_info.get("address1") or "",
        "address2": shop_info.get("address2") or "",
        "created_at": shop_info.get("created_at") or "",
    }


def _register_shopify_compliance_webhooks(
    shop: str,
    access_token: str,
    portal_config: PlatformConfiguration,
) -> None:
    """Register app/uninstalled and GDPR webhooks with Shopify after install."""
    from central_hub.integrations.models import ShopifyWebhookSubscription
    from central_hub.integrations.shopify.shopify_api import ShopifyAPIClient

    base = (portal_config.my_url or "").rstrip("/")
    webhook_url = f"{base}/api/v1/integrations/shopify/webhook/"
    topics = ["app/uninstalled", "customers/data_request", "customers/redact", "shop/redact"]
    try:
        client = ShopifyAPIClient(
            store_url=shop,
            access_token=access_token,
            api_version=SHOPIFY_API_VERSION,
        )
        for topic in topics:
            try:
                wh = client.create_webhook({"topic": topic, "address": webhook_url})
                sub_id = str(wh.get("id", ""))
                if sub_id:
                    ShopifyWebhookSubscription.objects.update_or_create(
                        shop_domain=shop,
                        topic=topic,
                        defaults={"subscription_id": sub_id, "callback_url": webhook_url},
                    )
                    logger.info("Registered Shopify webhook shop=%s topic=%s", shop, topic)
            except Exception as e:
                logger.warning("Failed to register webhook topic=%s for shop=%s: %s", topic, shop, e)
    except Exception as e:
        logger.warning("Shopify webhook registration failed for shop=%s: %s", shop, e)


# Mapping from config toggle keys to the Shopify webhook topics they require
_DATA_WEBHOOK_MAP = {
    "receive_products": ["products/create", "products/update", "products/delete"],
    "receive_customers": ["customers/create", "customers/update"],
    "receive_orders": ["orders/create", "orders/update"],
}


def reconcile_data_webhooks(config_obj) -> dict:
    """
    Register or unregister Shopify data webhooks to match the current config toggles.

    Called after every config save (PATCH). Idempotent — only subscribes topics that
    aren't already registered, and removes subscriptions for disabled toggles.

    Returns {"registered": [...], "removed": [...], "errors": [...]}.
    """
    from central_hub.integrations.models import ShopifyWebhookSubscription, ShopifyShopInstallation
    from central_hub.integrations.shopify.shopify_api import ShopifyAPIClient

    result = {"registered": [], "removed": [], "already": [], "errors": []}

    portal_config = _get_portal_config()
    if not portal_config or not portal_config.my_url:
        result["errors"].append("No platform URL configured")
        return result

    instance_id = config_obj.instance_id or "default"
    shop_domain = f"{instance_id}.myshopify.com" if ".myshopify.com" not in instance_id else instance_id

    installation = ShopifyShopInstallation.objects.filter(
        shop_domain=shop_domain,
        uninstalled_at__isnull=True,
    ).first()
    if not installation or not (installation.offline_access_token or "").strip():
        result["errors"].append(f"No active installation for {shop_domain}")
        return result

    base = portal_config.my_url.rstrip("/")
    webhook_url = f"{base}/api/v1/integrations/shopify/webhook/"
    cfg = config_obj.config or {}

    wanted_topics: set[str] = set()
    if config_obj.enabled and cfg.get("direction") == "receive":
        for toggle_key, topics in _DATA_WEBHOOK_MAP.items():
            if cfg.get(toggle_key):
                wanted_topics.update(topics)

    existing_subs = {
        sub.topic: sub
        for sub in ShopifyWebhookSubscription.objects.filter(shop_domain=shop_domain)
    }
    compliance_topics = {"app/uninstalled", "customers/data_request", "customers/redact", "shop/redact"}

    try:
        client = ShopifyAPIClient(
            store_url=shop_domain,
            access_token=installation.offline_access_token,
            api_version=(installation.api_version or SHOPIFY_API_VERSION).strip() or SHOPIFY_API_VERSION,
        )
    except Exception as e:
        result["errors"].append(f"API client init failed: {e}")
        return result

    for topic in wanted_topics:
        if topic in existing_subs:
            result["already"].append(topic)
            continue
        try:
            wh = client.create_webhook({"topic": topic, "address": webhook_url})
            sub_id = str(wh.get("id", ""))
            if sub_id:
                ShopifyWebhookSubscription.objects.update_or_create(
                    shop_domain=shop_domain,
                    topic=topic,
                    defaults={"subscription_id": sub_id, "callback_url": webhook_url},
                )
            result["registered"].append(topic)
            logger.info("Registered data webhook shop=%s topic=%s", shop_domain, topic)
        except Exception as e:
            result["errors"].append(f"{topic}: {e}")
            logger.warning("Failed to register data webhook topic=%s for shop=%s: %s", topic, shop_domain, e)

    for topic, sub in existing_subs.items():
        if topic in compliance_topics:
            continue
        if topic not in wanted_topics:
            try:
                if sub.subscription_id:
                    client.delete_webhook(sub.subscription_id)
                sub.delete()
                result["removed"].append(topic)
                logger.info("Removed data webhook shop=%s topic=%s", shop_domain, topic)
            except Exception as e:
                result["errors"].append(f"remove {topic}: {e}")
                logger.warning("Failed to remove webhook topic=%s for shop=%s: %s", topic, shop_domain, e)

    return result


def _verify_shopify_hmac(params: dict, secret: str) -> bool:
    """Verify the HMAC signature from Shopify OAuth redirect. Only 'hmac' is excluded from the message."""
    params_copy = {k: v for k, v in params.items() if k != "hmac"}
    hmac_value = params.get("hmac")
    if not hmac_value or not secret:
        return False
    sorted_params = "&".join(f"{k}={v}" for k, v in sorted(params_copy.items()))
    digest = hmac.new(secret.encode(), sorted_params.encode(), hashlib.sha256).hexdigest()
    return hmac.compare_digest(digest, hmac_value)


class ShopifyIntegrationAPIView(APIView):
    """Base for embed endpoints: accept either Shopify session token or moio JWT."""
    authentication_classes = [
        ShopifySessionTokenAuthentication,
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
        if not _validate_shop_domain(shop):
            return Response(
                {"error": "Invalid shop parameter. Must be a valid myshopify.com domain."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        portal_config = _get_portal_config()
        if not portal_config or not portal_config.shopify_client_id:
            return Response(
                {"error": "Shopify app credentials not configured. Set shopify_client_id in PlatformConfiguration."},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        redirect_uri = _build_redirect_uri(portal_config)
        state = secrets.token_urlsafe(32)
        ShopifyOAuthState.objects.create(state=state, shop_domain=shop)

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
        state_param = params.get("state", "").strip()

        if not shop or not code:
            return Response({"error": "shop and code are required"}, status=status.HTTP_400_BAD_REQUEST)
        if not _validate_shop_domain(shop):
            return Response(
                {"error": "Invalid shop parameter. Must be a valid myshopify.com domain."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        portal_config = _get_portal_config()
        if not portal_config or not portal_config.shopify_client_id or not portal_config.shopify_client_secret:
            return Response(
                {"error": "Shopify app credentials not configured"},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        # Verify HMAC (only 'hmac' key is excluded from the signed message per Shopify docs)
        if not _verify_shopify_hmac(dict(params), portal_config.shopify_client_secret):
            logger.warning("Shopify OAuth callback HMAC verification failed for shop=%s", shop)
            return Response({"error": "HMAC verification failed"}, status=status.HTTP_403_FORBIDDEN)

        # Validate state (CSRF protection)
        state_obj = ShopifyOAuthState.objects.filter(state=state_param).first()
        if not state_obj:
            logger.warning("Shopify OAuth callback: state not found or already used for shop=%s", shop)
            return Response({"error": "Invalid or expired state. Please try installing again."}, status=status.HTTP_403_FORBIDDEN)
        if state_obj.shop_domain != shop:
            logger.warning("Shopify OAuth callback: state shop mismatch for shop=%s", shop)
            state_obj.delete()
            return Response({"error": "State mismatch"}, status=status.HTTP_403_FORBIDDEN)
        now = timezone.now()
        if (now - state_obj.created_at).total_seconds() > OAUTH_STATE_TTL_SECONDS:
            state_obj.delete()
            return Response({"error": "State expired. Please try installing again."}, status=status.HTTP_403_FORBIDDEN)
        state_obj.delete()

        # Exchange code for access token (expiring=1 requests refresh_token for token rotation, Dec 2025+)
        try:
            resp = http_requests.post(
                f"https://{shop}/admin/oauth/access_token",
                json={
                    "client_id": portal_config.shopify_client_id,
                    "client_secret": portal_config.shopify_client_secret,
                    "code": code,
                    "expiring": 1,
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

        instance_id = _instance_id_for_shop(shop)

        # Compute expiry for expiring tokens (expires_in is seconds, typically 3600)
        expires_at = None
        if token_data.get("expires_in"):
            from datetime import timedelta
            expires_at = now + timedelta(seconds=int(token_data["expires_in"]))

        # Persist installation (source of truth per shop)
        installation, created = ShopifyShopInstallation.objects.update_or_create(
            shop_domain=shop,
            defaults={
                "offline_access_token": access_token,
                "refresh_token": token_data.get("refresh_token", "") or "",
                "offline_access_token_expires_at": expires_at,
                "scopes": SHOPIFY_SCOPES,
                "api_version": SHOPIFY_API_VERSION,
                "installed_at": now,
                "uninstalled_at": None,
                "last_seen_at": now,
            },
        )
        # update_or_create only applies defaults on create; for existing rows set token fields explicitly
        if not created:
            installation.offline_access_token = access_token
            installation.refresh_token = token_data.get("refresh_token", "") or ""
            installation.offline_access_token_expires_at = expires_at
            installation.last_seen_at = now
            installation.save(update_fields=["offline_access_token", "refresh_token", "offline_access_token_expires_at", "last_seen_at"])

        # Register GDPR/lifecycle webhooks with Shopify
        _register_shopify_compliance_webhooks(shop, access_token, portal_config)

        link = ShopifyShopLink.objects.filter(shop_domain=shop, status=ShopifyShopLinkStatus.LINKED).first()
        if link:
            tenant = link.tenant
            _ensure_shopify_integration_config(tenant, shop, installation)
            logger.info("Shopify OAuth: refreshed Installation and IntegrationConfig for linked shop=%s", shop)
        else:
            tenant = None
            logger.info("Shopify OAuth: installation saved for shop=%s; awaiting moio login/link", shop)

        # Redirect to the embedded-app frontend page (client_id lets the frontend bootstrap App Bridge)
        app_base = _shopify_embed_app_url(portal_config)
        redirect_to = (
            f"{app_base}?shop={shop}&host={host}&instance_id={instance_id}"
            f"&client_id={portal_config.shopify_client_id}"
        )
        return HttpResponseRedirect(redirect_to)


# ---------------------------------------------------------------------------
# Embed bootstrap – public, returns client_id so the embed page can create App Bridge
# ---------------------------------------------------------------------------

@method_decorator(csrf_exempt, name="dispatch")
class ShopifyEmbedBootstrapView(APIView):
    """
    GET /api/v1/integrations/shopify/embed/bootstrap/

    No auth. Returns shopify_client_id so the embedded page can create the App Bridge
    instance and obtain a session token. No secrets.
    """
    authentication_classes = []
    permission_classes = []

    def get(self, request):
        portal_config = _get_portal_config()
        if not portal_config or not portal_config.shopify_client_id:
            return Response(
                {"error": "Shopify app not configured"},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        return Response({"shopify_client_id": portal_config.shopify_client_id})


@method_decorator(csrf_exempt, name="dispatch")
class ShopifyEmbedLinkView(APIView):
    """
    POST /api/v1/integrations/shopify/embed/link/

    Authenticates the current moio user via JWT/session, verifies the Shopify
    session token from X-Shopify-Session-Token, provisions a tenant if needed,
    then links the Shopify shop to that tenant and materializes IntegrationConfig.
    """

    authentication_classes = [
        CsrfExemptSessionAuthentication,
        TenantJWTAAuthentication,
        ServiceJWTAuthentication,
    ]

    def post(self, request):
        user = getattr(request, "user", None)
        if not user or not getattr(user, "is_authenticated", False):
            return Response({"error": "Authentication required"}, status=status.HTTP_401_UNAUTHORIZED)
        if isinstance(getattr(request, "auth", None), dict):
            return Response({"error": "Human user authentication required"}, status=status.HTTP_403_FORBIDDEN)

        shopify_token = request.META.get("HTTP_X_SHOPIFY_SESSION_TOKEN", "").strip()
        if not shopify_token:
            return Response({"error": "Missing X-Shopify-Session-Token header"}, status=status.HTTP_400_BAD_REQUEST)

        try:
            payload = decode_shopify_session_token(shopify_token)
        except AuthenticationFailed as exc:
            err_msg = str(exc)
            err_msg += (
                " If you created a new Shopify app, update Platform Configuration "
                "(Client ID and Client Secret), then open the app again from Shopify Admin."
            )
            return Response({"error": err_msg}, status=status.HTTP_401_UNAUTHORIZED)

        shop = get_shop_domain_from_payload(payload) or ""
        if not _validate_shop_domain(shop):
            return Response({"error": "Invalid Shopify shop in session token"}, status=status.HTTP_400_BAD_REQUEST)

        installation = ShopifyShopInstallation.objects.filter(
            shop_domain=shop,
            uninstalled_at__isnull=True,
        ).first()
        if not installation:
            return Response(
                {"error": "Shopify app installation not found for this shop. Open the app from Shopify Admin to install it first."},
                status=status.HTTP_409_CONFLICT,
            )

        with transaction.atomic():
            tenant, created_tenant = _ensure_user_has_tenant(user, shop)
            existing_link = ShopifyShopLink.objects.filter(
                shop_domain=shop,
                status=ShopifyShopLinkStatus.LINKED,
            ).select_related("tenant").first()
            if existing_link and existing_link.tenant_id != tenant.id:
                return Response(
                    {
                        "error": (
                            f"This Shopify shop is already linked to another organization "
                            f"({getattr(existing_link.tenant, 'nombre', existing_link.tenant_id)})."
                        )
                    },
                    status=status.HTTP_409_CONFLICT,
                )

            link, _ = ShopifyShopLink.objects.update_or_create(
                shop_domain=shop,
                defaults={
                    "installation": installation,
                    "tenant": tenant,
                    "status": ShopifyShopLinkStatus.LINKED,
                    "linked_at": timezone.now(),
                    "linked_by_email": getattr(user, "email", "") or "",
                    "unlinked_at": None,
                    "unlinked_by_email": "",
                    "unlink_reason": "",
                },
            )
            _ensure_shopify_integration_config(tenant, shop, installation)

            # Test token immediately after linking
            from central_hub.integrations.shopify.service import test_stored_token_against_shopify
            test_result = test_stored_token_against_shopify(shop_domain=shop, call_products=False, call_inventory=False)
            logger.info("Shopify link: token test after link: ok=%s error=%s", test_result.get("ok"), test_result.get("error"))
            if not test_result.get("ok"):
                logger.warning("Shopify link: token test failed for shop=%s - token may need re-install", shop)

        return Response(
            {
                "ok": True,
                "shop": shop,
                "instance_id": _instance_id_for_shop(shop),
                "tenant_id": str(tenant.pk),
                "tenant_name": tenant.nombre,
                "tenant_created": created_tenant,
                "linked": link.status == ShopifyShopLinkStatus.LINKED,
            }
        )


# ---------------------------------------------------------------------------
# Embed config – supplies shop info to the React page (session token or moio auth)
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

        instance_id = _resolve_embed_instance_id(request, request.GET.get("instance_id", "default"))
        config_obj = IntegrationConfig.objects.filter(
            tenant=tenant, slug="shopify", instance_id=instance_id
        ).first()
        # If we have a config but it's missing store_url/access_token, persist from LINKED link when present
        if config_obj and isinstance(config_obj.config, dict):
            need_write = not (config_obj.config.get("store_url") or "").strip() or not (config_obj.config.get("access_token") or "").strip()
            if need_write:
                updated = ensure_shopify_config_persisted_from_link(tenant, instance_id)
                if updated:
                    config_obj = updated

        portal_config = _get_portal_config()
        cfg = config_obj.config if config_obj else {}
        shop_domain = (cfg.get("store_url") or getattr(request, "shopify_shop_domain", "") or "").strip()
        merchant_profile = {}
        merchant_profile_error = ""

        installation = None
        if shop_domain:
            installation = ShopifyShopInstallation.objects.filter(
                shop_domain=shop_domain,
                uninstalled_at__isnull=True,
            ).first()

        # Sync only works when there is a LINKED link for this tenant + shop; report disconnected otherwise
        has_linked_link = bool(
            shop_domain
            and ShopifyShopLink.objects.filter(
                shop_domain=shop_domain,
                tenant=tenant,
                status=ShopifyShopLinkStatus.LINKED,
            ).exists()
        )

        # Merchant profile is not fetched here; the frontend loads it independently from GET embed/merchant-profile/
        # so the config response is fast and never blocked by the Shopify API.

        # Report connected only when we have a LINKED link and installation has token (so sync will work)
        installation_has_token = bool(
            installation and (installation.offline_access_token or "").strip()
        )
        if not has_linked_link and shop_domain:
            effective_status = "pending_link"
            effective_access_token_set = False
        elif shop_domain and not installation_has_token:
            effective_status = "uninstalled"
            effective_access_token_set = False
        else:
            effective_status = (config_obj.status if config_obj else "pending_link")
            effective_access_token_set = bool(cfg.get("access_token")) if has_linked_link else False

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
            "merchant_profile": merchant_profile,
            "merchant_profile_error": merchant_profile_error,
            "instance_id": instance_id,
            "configured": config_obj is not None,
            "enabled": config_obj.enabled if config_obj else False,
            "status": effective_status,
            # Connection
            "store_url": cfg.get("store_url") or "",
            "access_token": _mask(cfg.get("access_token") or ""),
            "access_token_set": effective_access_token_set,
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
            # Sync cadence (minutes): 0 = webhooks only
            "sync_interval": int(cfg.get("sync_interval") or 0),
            # Sync metadata
            "last_sync_metadata": (config_obj.metadata or {}) if config_obj else {},
            # Active webhook subscriptions for this shop
            "webhook_subscriptions": _get_webhook_subscriptions_summary(shop_domain),
            # Chat widget (storefront): config for the embed block
            "chat_widget": _get_chat_widget_config_for_embed(cfg),
        }
        return Response(data)

    def patch(self, request):
        """
        Save Shopify settings from the embedded app.

        Two modes:
        - Platform settings (app_url, client credentials): platform-admin only
        - Tenant integration settings (enabled, direction, toggles, api_version): authenticated shop/tenant user
        """
        tenant = self.get_tenant()
        if not tenant:
            return Response({"error": "Authentication required"}, status=status.HTTP_401_UNAUTHORIZED)
        user = getattr(request, "user", None)
        if not user or not getattr(user, "is_authenticated", True):
            return Response({"error": "Authentication required"}, status=status.HTTP_401_UNAUTHORIZED)

        data = request.data
        platform_fields_present = any(
            str(data.get(field, "") or "").strip()
            for field in ("app_url", "shopify_client_id", "shopify_client_secret")
        )

        if not platform_fields_present:
            requested_instance_id = (
                str(request.query_params.get("instance_id") or data.get("instance_id") or "").strip()
            )
            instance_id = _resolve_embed_instance_id(request, requested_instance_id)

            config_obj = IntegrationConfig.objects.filter(
                tenant=tenant,
                slug="shopify",
                instance_id=instance_id,
            ).first()

            if not config_obj:
                shop_domain = str(getattr(request, "shopify_shop_domain", "") or "").strip()
                installation = None
                if shop_domain:
                    installation = ShopifyShopInstallation.objects.filter(
                        shop_domain=shop_domain,
                        uninstalled_at__isnull=True,
                    ).first()
                if not installation or not shop_domain:
                    return Response(
                        {"error": "Shopify integration not configured for this shop yet."},
                        status=status.HTTP_409_CONFLICT,
                    )
                config_obj = _ensure_shopify_integration_config(tenant, shop_domain, installation)

            config_patch = dict(data.get("config") or {})
            allowed_keys = {
                "api_version",
                "direction",
                "receive_products",
                "receive_customers",
                "receive_orders",
                "receive_inventory",
                "send_inventory_updates",
                "send_order_updates",
                "sync_interval",
            }
            for key, value in config_patch.items():
                if key in allowed_keys:
                    config_obj.config[key] = value
            # Merge chat_widget config (storefront widget)
            if "chat_widget" in config_patch:
                cw = config_obj.config.setdefault("chat_widget", {})
                if isinstance(config_patch["chat_widget"], dict):
                    patch_cw = config_patch["chat_widget"]
                    for field in ("enabled", "title", "bubble_icon", "greeting", "primary_color", "allowed_templates"):
                        if field in patch_cw:
                            cw[field] = patch_cw[field]
                    if "position" in patch_cw:
                        raw_position = str(patch_cw.get("position", "")).strip() or "bottom-right"
                        cw["position"] = raw_position if raw_position in _CHAT_WIDGET_POSITIONS else "bottom-right"
                    if "offset_x" in patch_cw:
                        cw["offset_x"] = _int_in_range(patch_cw.get("offset_x"), default=20, minimum=0, maximum=64)
                    if "offset_y" in patch_cw:
                        cw["offset_y"] = _int_in_range(patch_cw.get("offset_y"), default=20, minimum=0, maximum=96)
                    if "bubble_size" in patch_cw:
                        cw["bubble_size"] = _int_in_range(patch_cw.get("bubble_size"), default=56, minimum=44, maximum=72)
                    if "window_width" in patch_cw:
                        cw["window_width"] = _int_in_range(patch_cw.get("window_width"), default=360, minimum=280, maximum=520)
                    if "window_height" in patch_cw:
                        cw["window_height"] = _int_in_range(patch_cw.get("window_height"), default=480, minimum=320, maximum=760)
                config_obj.config["chat_widget"] = cw

            if "enabled" in data:
                config_obj.enabled = bool(data.get("enabled"))

            config_obj.save()

            # Reconcile Shopify data webhooks to match the new toggle state
            try:
                wh_result = reconcile_data_webhooks(config_obj)
                logger.info("reconcile_data_webhooks result for %s: %s", config_obj.instance_id, wh_result)
            except Exception as e:
                logger.warning("reconcile_data_webhooks failed for %s: %s", config_obj.instance_id, e)
                wh_result = {"errors": [str(e)]}

            # Reconcile periodic sync schedule based on sync_interval
            try:
                _reconcile_periodic_sync(config_obj)
            except Exception as e:
                logger.warning("_reconcile_periodic_sync failed for %s: %s", config_obj.instance_id, e)

            return Response({
                "ok": True,
                "instance_id": config_obj.instance_id,
                "enabled": config_obj.enabled,
                "webhooks": wh_result,
            })

        if not getattr(user, "is_superuser", False) and not user_has_role(user, "platform_admin"):
            return Response(
                {"error": "Only platform administrators can update Shopify app credentials and app URL."},
                status=status.HTTP_403_FORBIDDEN,
            )

        portal_config = _get_portal_config()
        if not portal_config:
            return Response({"error": "Platform configuration not found"}, status=status.HTTP_404_NOT_FOUND)

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


class ShopifyEmbedMerchantProfileView(ShopifyIntegrationAPIView):
    """
    GET /api/v1/integrations/shopify/embed/merchant-profile/?instance_id=<id>

    Returns only merchant_profile and merchant_profile_error. Load this independently
    in the frontend so the main config response is never blocked by the Shopify API.
    """

    def get(self, request):
        tenant = self.get_tenant()
        if not tenant:
            return Response({"error": "Authentication required"}, status=status.HTTP_401_UNAUTHORIZED)

        instance_id = _resolve_embed_instance_id(request, request.GET.get("instance_id", "default"))
        config_obj = IntegrationConfig.objects.filter(
            tenant=tenant, slug="shopify", instance_id=instance_id
        ).first()
        cfg = config_obj.config if config_obj else {}
        shop_domain = (cfg.get("store_url") or getattr(request, "shopify_shop_domain", "") or "").strip()

        merchant_profile = {}
        merchant_profile_error = ""

        if shop_domain:
            installation = ShopifyShopInstallation.objects.filter(
                shop_domain=shop_domain,
                uninstalled_at__isnull=True,
            ).first()
            if installation and (installation.offline_access_token or "").strip():
                try:
                    from central_hub.integrations.shopify.shopify_api import ShopifyAPIClient  # noqa: PLC0415

                    client = ShopifyAPIClient(
                        store_url=shop_domain,
                        access_token=installation.offline_access_token,
                        api_version=(installation.api_version or cfg.get("api_version") or SHOPIFY_API_VERSION),
                    )
                    merchant_profile = _serialize_shopify_merchant_profile(client.get_shop_info())
                except Exception as exc:
                    merchant_profile_error = str(exc)
                    logger.warning("Failed to fetch Shopify merchant profile for shop=%s: %s", shop_domain, exc)

        return Response({
            "merchant_profile": merchant_profile,
            "merchant_profile_error": merchant_profile_error,
        })


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

        requested = (request.data.get("instance_id") or "default").strip()
        instance_id = _resolve_embed_instance_id(request, requested)
        if requested != instance_id:
            logger.info("Shopify embed sync: resolved instance_id %s -> %s", requested, instance_id)
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

            tid = int(tenant.pk)
            if sync_type == "products":
                task = shopify_tasks.sync_shopify_products.delay(
                    tenant_id=tid, instance_id=instance_id
                )
            elif sync_type == "customers":
                task = shopify_tasks.sync_shopify_customers.delay(
                    tenant_id=tid, instance_id=instance_id
                )
            elif sync_type == "orders":
                task = shopify_tasks.sync_shopify_orders.delay(
                    tenant_id=tid, instance_id=instance_id
                )
            else:
                task = shopify_tasks.sync_all_shopify_data.delay(
                    tenant_id=tid, instance_id=instance_id
                )

            return Response({"status": "queued", "task_id": task.id, "sync_type": sync_type})
        except Exception as exc:
            logger.exception("Failed to queue Shopify sync task")
            return Response({"error": str(exc)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@method_decorator(csrf_exempt, name="dispatch")
class ShopifyEmbedTestView(ShopifyIntegrationAPIView):
    """
    POST /api/v1/integrations/shopify/embed/test/

    Body: { "instance_id": "...", "checks": { "products": true, "customers": true, "orders": false, "inventory": true } }

    Queues test_shopify_connection for each resource the caller wants verified.
    """

    def post(self, request):
        tenant = self.get_tenant()
        if not tenant:
            return Response({"error": "Authentication required"}, status=status.HTTP_401_UNAUTHORIZED)

        requested = (request.data.get("instance_id") or "default").strip()
        instance_id = _resolve_embed_instance_id(request, requested)

        checks = request.data.get("checks") or {}

        try:
            from central_hub.integrations.shopify import tasks as shopify_tasks

            task = shopify_tasks.test_shopify_connection.delay(
                tenant_id=int(tenant.pk),
                instance_id=instance_id,
                call_products=bool(checks.get("products", True)),
                call_customers=bool(checks.get("customers", False)),
                call_orders=bool(checks.get("orders", False)),
                call_inventory=bool(checks.get("inventory", True)),
            )
            return Response({"status": "queued", "task_id": task.id})
        except Exception as exc:
            logger.exception("Failed to queue Shopify test task")
            return Response({"error": str(exc)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class ShopifyEmbedSyncStatusView(ShopifyIntegrationAPIView):
    """
    GET /api/v1/integrations/shopify/embed/sync-status/?task_id=<id>

    Returns Celery task status for polling after triggering a sync.
    """

    def get(self, request):
        tenant = self.get_tenant()
        if not tenant:
            return Response({"error": "Authentication required"}, status=status.HTTP_401_UNAUTHORIZED)

        task_id = (request.GET.get("task_id") or "").strip()
        if not task_id:
            return Response({"error": "task_id is required"}, status=status.HTTP_400_BAD_REQUEST)

        from celery.result import AsyncResult

        from moio_platform.celery_app import app

        result = AsyncResult(task_id, app=app)
        payload = {
            "task_id": task_id,
            "status": result.status,
            "ready": result.ready(),
        }
        if result.ready():
            payload["successful"] = result.successful()
            if result.successful() and result.result:
                payload["result"] = result.result
            elif not result.successful() and result.result:
                payload["error"] = str(result.result)
        return Response(payload)


# ---------------------------------------------------------------------------
# Chat widget config (public, for storefront script)
# ---------------------------------------------------------------------------

def _chat_widget_config_response_for_shop(shop: str) -> tuple[Response | None, Response]:
    """
    Build the chat widget config JSON response for a given shop.
    Returns (None, response) on success, (error_response, _) on validation/not-found.
    """
    if not shop or not _validate_shop_domain(shop):
        return (
            Response(
                {"error": "Invalid shop. Must be a valid myshopify.com domain."},
                status=status.HTTP_400_BAD_REQUEST,
            ),
            None,
        )
    link = ShopifyShopLink.objects.filter(
        shop_domain=shop,
        status=ShopifyShopLinkStatus.LINKED,
    ).select_related("tenant").first()
    if not link or not link.tenant_id:
        return Response({"enabled": False, "error": "Shop not linked"}, status=status.HTTP_404_NOT_FOUND), None
    installation = ShopifyShopInstallation.objects.filter(
        shop_domain=shop,
        uninstalled_at__isnull=True,
    ).first()
    if not installation or not (installation.offline_access_token or "").strip():
        return Response({"enabled": False, "error": "App not installed"}, status=status.HTTP_404_NOT_FOUND), None
    instance_id = _instance_id_for_shop(shop)
    config_obj = IntegrationConfig.objects.filter(
        tenant=link.tenant,
        slug="shopify",
        instance_id=instance_id,
    ).first()
    if not config_obj:
        return Response({"enabled": False}, status=status.HTTP_200_OK), None
    cfg = config_obj.config or {}
    cw = cfg.get("chat_widget") or {}
    if not isinstance(cw, dict):
        cw = {}
    position = str(cw.get("position", "")).strip() or "bottom-right"
    if position not in _CHAT_WIDGET_POSITIONS:
        position = "bottom-right"
    portal_config = _get_portal_config()
    base_url = (portal_config.my_url or "").rstrip("/") if portal_config else ""
    ws_url = ""
    if base_url:
        ws_base = base_url.replace("https://", "wss://", 1).replace("http://", "ws://", 1)
        ws_url = f"{ws_base}/ws/shopify-chat/"
    return None, Response({
        "enabled": True,
        "title": str(cw.get("title", "")).strip() or "Chat",
        "bubble_icon": str(cw.get("bubble_icon", "")).strip() or "💬",
        "greeting": str(cw.get("greeting", "")).strip() or "Hello! How can we help?",
        "primary_color": str(cw.get("primary_color", "")).strip() or "#000000",
        "position": position,
        "offset_x": _int_in_range(cw.get("offset_x"), default=20, minimum=0, maximum=64),
        "offset_y": _int_in_range(cw.get("offset_y"), default=20, minimum=0, maximum=96),
        "bubble_size": _int_in_range(cw.get("bubble_size"), default=56, minimum=44, maximum=72),
        "window_width": _int_in_range(cw.get("window_width"), default=360, minimum=280, maximum=520),
        "window_height": _int_in_range(cw.get("window_height"), default=480, minimum=320, maximum=760),
        "allowed_templates": cw.get("allowed_templates") if isinstance(cw.get("allowed_templates"), list) else None,
        "ws_url": ws_url,
    })


def _verify_shopify_app_proxy_signature(request, secret: str) -> bool:
    """
    Verify Shopify app proxy HMAC. Query params are signed (excluding 'signature').
    Message: sorted key=value pairs, concatenated (no separator). HMAC-SHA256 hex.
    """
    if not secret:
        return False
    params = request.GET.dict()
    signature = params.pop("signature", None)
    if not signature:
        return False
    # Build message per Shopify: sort by key, each "key=value" (array values joined by comma)
    parts = []
    for k in sorted(params.keys()):
        v = params[k]
        if isinstance(v, list):
            v = ",".join(str(x) for x in v)
        parts.append(f"{k}={v}")
    message = "".join(parts)
    digest = hmac.new(secret.encode(), message.encode(), hashlib.sha256).hexdigest()
    return hmac.compare_digest(digest, signature)


@method_decorator(csrf_exempt, name="dispatch")
class ShopifyChatWidgetConfigView(APIView):
    """
    GET /api/v1/integrations/shopify/chat-widget-config/?shop=xxx.myshopify.com

    Public endpoint for the storefront chat widget script. Returns widget config
    (enabled, title, greeting, colors, position, allowed_templates, ws_url). No auth;
    validates that the shop has the app installed and linked.
    """

    authentication_classes = []
    permission_classes = []

    def get(self, request):
        shop = (request.GET.get("shop") or "").strip()
        if not shop:
            return Response({"error": "shop is required"}, status=status.HTTP_400_BAD_REQUEST)
        err, resp = _chat_widget_config_response_for_shop(shop)
        if err is not None:
            return err
        return resp


@method_decorator(csrf_exempt, name="dispatch")
class ShopifyAppProxyView(APIView):
    """
    Handles Shopify app proxy requests. Storefront calls e.g.:
    https://{shop}/apps/moio-chat/chat-widget-config?shop=...
    Shopify forwards to this view with shop, path_prefix, timestamp, signature, etc.
    Verify signature then serve chat-widget-config so the theme extension needs no API base URL.
    """

    authentication_classes = []
    permission_classes = []

    def get(self, request, path: str = ""):
        portal_config = _get_portal_config()
        if not portal_config or not (portal_config.shopify_client_secret or "").strip():
            return Response({"error": "App proxy not configured"}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
        if not _verify_shopify_app_proxy_signature(request, portal_config.shopify_client_secret):
            logger.warning("Shopify app proxy signature verification failed")
            return Response({"error": "Invalid signature"}, status=status.HTTP_403_FORBIDDEN)
        shop = (request.GET.get("shop") or "").strip()
        path_normalized = (path or "").strip().strip("/")
        if path_normalized == "chat-widget-config" and shop:
            err, resp = _chat_widget_config_response_for_shop(shop)
            if err is not None:
                return err
            return resp
        return Response({"error": "Not found"}, status=status.HTTP_404_NOT_FOUND)


