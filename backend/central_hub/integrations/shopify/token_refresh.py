"""
Shopify offline access token refresh (expiring tokens, Dec 2025+).

When an installation has a refresh_token and the access token is expired or about to expire,
call refresh_shopify_installation_token() to obtain a new access_token and refresh_token.
"""

from __future__ import annotations

import logging
from datetime import timedelta

from django.utils import timezone

from central_hub.integrations.models import ShopifyShopInstallation
from central_hub.models import PlatformConfiguration

logger = logging.getLogger(__name__)

# Refresh if token expires within this many seconds
REFRESH_BUFFER_SECONDS = 300  # 5 minutes


def refresh_shopify_installation_token(installation: ShopifyShopInstallation) -> bool:
    """
    Exchange the installation's refresh_token for a new access_token and refresh_token.
    Updates the installation in place. Returns True if refresh succeeded, False otherwise.
    """
    refresh_token = (installation.refresh_token or "").strip()
    if not refresh_token:
        return False
    portal = PlatformConfiguration.objects.first()
    if not portal or not portal.shopify_client_id or not portal.shopify_client_secret:
        logger.warning("Shopify token refresh: platform credentials not configured")
        return False
    shop = installation.shop_domain
    try:
        import requests
        resp = requests.post(
            f"https://{shop}/admin/oauth/access_token",
            json={
                "client_id": portal.shopify_client_id,
                "client_secret": portal.shopify_client_secret,
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
            },
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()
        new_access = (data.get("access_token") or "").strip()
        if not new_access:
            logger.warning("Shopify token refresh: no access_token in response for shop=%s", shop)
            return False
        now = timezone.now()
        expires_at = None
        if data.get("expires_in"):
            expires_at = now + timedelta(seconds=int(data["expires_in"]))
        installation.offline_access_token = new_access
        installation.refresh_token = (data.get("refresh_token") or "") or installation.refresh_token
        installation.offline_access_token_expires_at = expires_at
        installation.last_seen_at = now
        installation.save(update_fields=[
            "offline_access_token", "refresh_token", "offline_access_token_expires_at", "last_seen_at", "updated_at"
        ])
        logger.info("Shopify token refresh: new access token for shop=%s", shop)
        return True
    except Exception as e:
        logger.warning("Shopify token refresh failed for shop=%s: %s", shop, e)
        return False


def installation_token_needs_refresh(installation: ShopifyShopInstallation) -> bool:
    """Return True if the installation has a refresh_token and the access token is expired or expiring soon."""
    if not (installation.refresh_token or "").strip():
        return False
    expires_at = getattr(installation, "offline_access_token_expires_at", None)
    if expires_at is None:
        return False  # non-expiring token, no refresh needed
    now = timezone.now()
    return now >= (expires_at - timedelta(seconds=REFRESH_BUFFER_SECONDS))
