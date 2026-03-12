"""
Tests for Shopify OAuth state validation and webhook HMAC verification.
"""
import base64
import hashlib
import hmac as hmac_lib
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from central_hub.integrations.models import ShopifyOAuthState
from central_hub.integrations.shopify.webhook_receiver import _verify_shopify_webhook_hmac, shopify_webhook_receiver
from central_hub.models import PlatformConfiguration


class ShopifyOAuthStateTests(TestCase):
    """OAuth state is persisted and can be validated."""

    def test_state_created_and_retrieved(self):
        state = "abc123"
        shop = "mystore.myshopify.com"
        ShopifyOAuthState.objects.create(state=state, shop_domain=shop)
        obj = ShopifyOAuthState.objects.filter(state=state).first()
        self.assertIsNotNone(obj)
        self.assertEqual(obj.shop_domain, shop)

    def test_state_delete_after_use(self):
        state = "xyz789"
        shop = "other.myshopify.com"
        ShopifyOAuthState.objects.create(state=state, shop_domain=shop)
        obj = ShopifyOAuthState.objects.get(state=state)
        obj.delete()
        self.assertIsNone(ShopifyOAuthState.objects.filter(state=state).first())


class ShopifyWebhookHmacTests(TestCase):
    """Webhook HMAC verification accepts valid signatures and rejects invalid."""

    def test_verify_valid_hmac(self):
        secret = "my_secret"
        body = b'{"id": 123}'
        computed = hmac_lib.new(secret.encode(), body, hashlib.sha256).digest()
        sig = base64.b64encode(computed).decode("ascii")
        self.assertTrue(_verify_shopify_webhook_hmac(body, sig, secret))

    def test_verify_rejects_wrong_secret(self):
        body = b'{"id": 123}'
        sig = base64.b64encode(hmac_lib.new(b"right", body, hashlib.sha256).digest()).decode("ascii")
        self.assertFalse(_verify_shopify_webhook_hmac(body, sig, "wrong_secret"))

    def test_verify_rejects_tampered_body(self):
        secret = "my_secret"
        body = b'{"id": 123}'
        sig = base64.b64encode(hmac_lib.new(secret.encode(), body, hashlib.sha256).digest()).decode("ascii")
        self.assertFalse(_verify_shopify_webhook_hmac(b'{"id": 456}', sig, secret))

    def test_verify_rejects_empty_signature(self):
        self.assertFalse(_verify_shopify_webhook_hmac(b"{}", "", "secret"))


@override_settings(ROOT_URLCONF="moio_platform.urls")
class ShopifyWebhookReceiverTests(TestCase):
    """Webhook receiver returns 401 on invalid HMAC and 200 on valid GDPR topics."""

    def setUp(self):
        self.client = APIClient()
        self.portal = PlatformConfiguration.objects.create(
            my_url="https://example.com/",
            shopify_client_id="client",
            shopify_client_secret="webhook_secret_key",
        )
        self.webhook_url = "/api/v1/integrations/shopify/webhook/"

    def test_webhook_rejects_invalid_hmac(self):
        body = b'{"shop_id": 1}'
        res = self.client.post(
            self.webhook_url,
            data=body,
            content_type="application/json",
            HTTP_X_SHOPIFY_TOPIC="shop/redact",
            HTTP_X_SHOPIFY_SHOP_DOMAIN="store.myshopify.com",
            HTTP_X_SHOPIFY_HMAC_SHA256="invalid",
        )
        self.assertEqual(res.status_code, 401)

    def test_webhook_accepts_valid_hmac_for_shop_redact(self):
        secret = self.portal.shopify_client_secret
        body = b'{"shop_id": 12345}'
        sig = base64.b64encode(hmac_lib.new(secret.encode(), body, hashlib.sha256).digest()).decode("ascii")
        res = self.client.post(
            self.webhook_url,
            data=body,
            content_type="application/json",
            HTTP_X_SHOPIFY_TOPIC="shop/redact",
            HTTP_X_SHOPIFY_SHOP_DOMAIN="store.myshopify.com",
            HTTP_X_SHOPIFY_HMAC_SHA256=sig,
        )
        self.assertEqual(res.status_code, 200)

    def test_webhook_requires_topic_and_shop_headers(self):
        res = self.client.post(
            self.webhook_url,
            data=b"{}",
            content_type="application/json",
        )
        self.assertEqual(res.status_code, 400)
