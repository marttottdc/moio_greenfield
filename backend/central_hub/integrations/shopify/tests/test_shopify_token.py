"""
Test that the stored Shopify token can read from Shopify API.

Run with a real shop to verify token and sync path:
  SHOPIFY_TEST_SHOP=moioplatform.myshopify.com python manage.py test central_hub.integrations.shopify.tests.test_shopify_token
Or with tenant + instance (same path as sync tasks):
  SHOPIFY_TEST_TENANT_ID=1 SHOPIFY_TEST_INSTANCE_ID=moioplatform python manage.py test central_hub.integrations.shopify.tests.test_shopify_token
"""
import os
from django.test import TestCase, override_settings

from central_hub.integrations.shopify.service import test_stored_token_against_shopify


@override_settings(ROOT_URLCONF="moio_platform.urls")
class TestStoredTokenAgainstShopify(TestCase):
    """
    Uses the stored token to call Shopify REST API (shop + products).
    Skipped unless SHOPIFY_TEST_SHOP or (SHOPIFY_TEST_TENANT_ID + SHOPIFY_TEST_INSTANCE_ID) are set.
    """

    def test_stored_token_by_shop_domain(self) -> None:
        shop = (os.environ.get("SHOPIFY_TEST_SHOP") or "").strip()
        if not shop:
            self.skipTest("Set SHOPIFY_TEST_SHOP (e.g. moioplatform.myshopify.com) to run this test")
        result = test_stored_token_against_shopify(shop_domain=shop, call_products=True)
        self.assertTrue(result["ok"], msg=result.get("error") or "Token test failed")
        self.assertIsNotNone(result.get("shop_info"), "Expected shop_info in result")
        self.assertIn("name", result["shop_info"] or {})

    def test_stored_token_by_tenant_and_instance_id(self) -> None:
        """Same resolution path as sync tasks (get_shopify_config_for_sync)."""
        tenant_id_str = (os.environ.get("SHOPIFY_TEST_TENANT_ID") or "").strip()
        instance_id = (os.environ.get("SHOPIFY_TEST_INSTANCE_ID") or "").strip()
        if not tenant_id_str or not instance_id:
            self.skipTest("Set SHOPIFY_TEST_TENANT_ID and SHOPIFY_TEST_INSTANCE_ID to run this test")
        try:
            tenant_id = int(tenant_id_str)
        except ValueError:
            self.skipTest("SHOPIFY_TEST_TENANT_ID must be an integer")
        result = test_stored_token_against_shopify(
            tenant_id=tenant_id,
            instance_id=instance_id,
            call_products=True,
        )
        self.assertTrue(result["ok"], msg=result.get("error") or "Token test failed")
        self.assertIsNotNone(result.get("shop_info"), "Expected shop_info in result")
