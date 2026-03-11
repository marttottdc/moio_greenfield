"""
Shopify embedded app URL patterns.

Mounted at /api/v1/integrations/shopify/ (see central_hub/integrations/urls.py)
"""

from django.urls import path

from .views import (
    ShopifyOAuthInstallView,
    ShopifyOAuthCallbackView,
    ShopifyEmbedConfigView,
    ShopifyEmbedSyncView,
)

urlpatterns = [
    # OAuth flow
    path("oauth/install/", ShopifyOAuthInstallView.as_view(), name="shopify_oauth_install"),
    path("oauth/callback/", ShopifyOAuthCallbackView.as_view(), name="shopify_oauth_callback"),
    # Embedded-app helpers (used by the React page served inside Shopify admin)
    path("embed/config/", ShopifyEmbedConfigView.as_view(), name="shopify_embed_config"),
    path("embed/sync/", ShopifyEmbedSyncView.as_view(), name="shopify_embed_sync"),
]
