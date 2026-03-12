"""
Shopify embedded app URL patterns.

Mounted at /api/v1/integrations/shopify/ (see central_hub/integrations/urls.py)
"""

from django.urls import path

from .views import (
    ShopifyOAuthInstallView,
    ShopifyOAuthCallbackView,
    ShopifyEmbedBootstrapView,
    ShopifyEmbedLinkView,
    ShopifyEmbedConfigView,
    ShopifyEmbedMerchantProfileView,
    ShopifyEmbedSyncView,
    ShopifyEmbedSyncStatusView,
    ShopifyEmbedTestView,
    ShopifyChatWidgetConfigView,
    ShopifyAppProxyView,
)
from .webhook_receiver import shopify_webhook_receiver

urlpatterns = [
    # OAuth flow
    path("oauth/install/", ShopifyOAuthInstallView.as_view(), name="shopify_oauth_install"),
    path("oauth/callback/", ShopifyOAuthCallbackView.as_view(), name="shopify_oauth_callback"),
    # Webhook: single endpoint with HMAC verification and GDPR/lifecycle handlers
    path("webhook/", shopify_webhook_receiver, name="shopify_webhook_receiver"),
    # Embedded-app: bootstrap (public) and config/sync (session token or moio JWT)
    path("embed/bootstrap/", ShopifyEmbedBootstrapView.as_view(), name="shopify_embed_bootstrap"),
    path("embed/link/", ShopifyEmbedLinkView.as_view(), name="shopify_embed_link"),
    path("embed/config/", ShopifyEmbedConfigView.as_view(), name="shopify_embed_config"),
    path("embed/merchant-profile/", ShopifyEmbedMerchantProfileView.as_view(), name="shopify_embed_merchant_profile"),
    path("embed/sync/", ShopifyEmbedSyncView.as_view(), name="shopify_embed_sync"),
    path("embed/sync-status/", ShopifyEmbedSyncStatusView.as_view(), name="shopify_embed_sync_status"),
    path("embed/test/", ShopifyEmbedTestView.as_view(), name="shopify_embed_test"),
    # Public: storefront chat widget config (no auth)
    path("chat-widget-config/", ShopifyChatWidgetConfigView.as_view(), name="shopify_chat_widget_config"),
    # App proxy: storefront requests to /apps/moio-chat/... are forwarded here (no API base URL needed in theme)
    path("app-proxy/<path:path>", ShopifyAppProxyView.as_view(), name="shopify_app_proxy"),
]
