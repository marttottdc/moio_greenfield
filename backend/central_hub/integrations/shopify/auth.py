"""
Shopify embedded app session-token authentication.

Verifies JWTs issued by Shopify App Bridge (getSessionToken) using the app's
client secret. Resolves the shop from the token and attaches the linked tenant
to the request so embed views can authorize without requiring a moio JWT.
"""

from __future__ import annotations

import logging
from typing import Any

import jwt
from rest_framework.authentication import BaseAuthentication
from rest_framework.exceptions import AuthenticationFailed

from central_hub.integrations.models import ShopifyShopLink, ShopifyShopLinkStatus
from central_hub.models import PlatformConfiguration

logger = logging.getLogger(__name__)


def _get_portal_config() -> PlatformConfiguration | None:
    """Use public-request helper so OAuth callback (external, no tenant) always sees the row."""
    from central_hub.config import get_platform_configuration_for_public_request
    return get_platform_configuration_for_public_request()


def decode_shopify_session_token(token: str) -> dict[str, Any]:
    """
    Decode and verify a Shopify App Bridge session token.

    This validates the token signature/audience but does not require the shop to
    already be linked to a tenant. That allows onboarding flows to authenticate
    the moio user first and then create the ShopifyShopLink explicitly.
    """
    portal_config = _get_portal_config()
    if not portal_config or not portal_config.shopify_client_id or not portal_config.shopify_client_secret:
        raise AuthenticationFailed("Shopify app credentials are not configured")

    try:
        return jwt.decode(
            token,
            portal_config.shopify_client_secret,
            algorithms=["HS256"],
            audience=portal_config.shopify_client_id,
            leeway=10,
        )
    except jwt.ExpiredSignatureError as exc:
        raise AuthenticationFailed("Shopify session token has expired") from exc
    except jwt.InvalidTokenError as exc:
        logger.debug("Shopify session token invalid: %s", exc)
        raise AuthenticationFailed("Invalid Shopify session token") from exc


def get_shop_domain_from_payload(payload: dict[str, Any]) -> str | None:
    dest = payload.get("dest") or payload.get("shop")
    if not dest:
        return None
    return dest.replace("https://", "").replace("http://", "").split("/")[0].strip()


class ShopifySessionTokenAuthentication(BaseAuthentication):
    """
    Authenticate requests using a Shopify session token (JWT from App Bridge).

    Expects Authorization: Bearer <session_token>. Verifies the JWT with the
    app's client secret, extracts the shop (dest), resolves the tenant via
    ShopifyShopLink, and attaches a minimal user with request.user.tenant set.
    """

    def authenticate(self, request) -> tuple[Any, Any] | None:
        auth_header = request.META.get("HTTP_AUTHORIZATION", "")
        if not auth_header.startswith("Bearer "):
            return None
        token = auth_header[7:].strip()
        if not token:
            return None

        try:
            payload = decode_shopify_session_token(token)
        except AuthenticationFailed:
            return None

        shop_domain = get_shop_domain_from_payload(payload)
        if not shop_domain:
            return None

        link = ShopifyShopLink.objects.filter(
            shop_domain=shop_domain,
            status=ShopifyShopLinkStatus.LINKED,
        ).select_related("tenant").first()
        if not link:
            logger.warning("Shopify session token: no linked tenant for shop=%s", shop_domain)
            raise AuthenticationFailed(
                "Shop not linked to an organization. Sign in to moio inside the Shopify app to finish setup."
            )

        class ShopifyEmbedUser:
            is_authenticated = True
            tenant = link.tenant

            def __str__(self):
                return f"shopify:{shop_domain}"

        request.shopify_shop_domain = shop_domain
        request.shopify_session_payload = payload
        return (ShopifyEmbedUser(), None)

    def authenticate_header(self, request):
        return 'Bearer realm="shopify_session"'
