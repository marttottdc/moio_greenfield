"""
Tests for test_shopify_connection task – API access check only, no sync.

Uses mocks so no real Shopify calls are made.
"""
from unittest.mock import patch

from django.test import TestCase

from central_hub.integrations.shopify.tasks import test_shopify_connection


@patch("central_hub.integrations.shopify.tasks.test_stored_token_against_shopify")
class TestShopifyConnectionTask(TestCase):
    """Verify test_shopify_connection task only makes API calls, does not sync."""

    def test_returns_ok_when_token_valid(self, mock_test: "patch") -> None:
        mock_test.return_value = {
            "ok": True,
            "shop_info": {"name": "Test Shop", "domain": "test.myshopify.com"},
            "products_preview": [],
            "inventory_preview": [],
            "error": None,
            "status_code": None,
        }
        result = test_shopify_connection(tenant_id=1, instance_id="test-instance")
        self.assertEqual(result["status"], "ok")
        self.assertIn("shop_info", result)
        self.assertIn("test_result", result)
        mock_test.assert_called_once_with(
            tenant_id=1,
            instance_id="test-instance",
            call_products=True,
            call_inventory=True,
        )

    def test_returns_failed_when_token_invalid(self, mock_test: "patch") -> None:
        mock_test.return_value = {
            "ok": False,
            "shop_info": None,
            "products_preview": None,
            "inventory_preview": None,
            "error": "401 Unauthorized",
            "status_code": 401,
        }
        result = test_shopify_connection(tenant_id=1, instance_id="test-instance")
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["error"], "401 Unauthorized")
        self.assertEqual(result["status_code"], 401)

    def test_passes_instance_id_default(self, mock_test: "patch") -> None:
        mock_test.return_value = {"ok": True, "shop_info": {}, "error": None}
        test_shopify_connection(tenant_id=1)
        mock_test.assert_called_once_with(
            tenant_id=1,
            instance_id="default",
            call_products=True,
            call_inventory=True,
        )
