"""
Test that the stored Shopify token can read from Shopify API.

Usage:
  # By shop domain (uses ShopifyShopInstallation token directly)
  python manage.py shopify_test_token moioplatform.myshopify.com

  # By tenant + instance_id (same path as sync tasks: get_shopify_config_for_sync)
  python manage.py shopify_test_token --tenant 1 --instance-id moioplatform
"""
from __future__ import annotations

import json
from django.core.management.base import BaseCommand

from central_hub.integrations.shopify.service import test_stored_token_against_shopify


class Command(BaseCommand):
    help = "Use the stored Shopify token to call Shopify API (shop + products). Fails with clear error if token is invalid."

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "shop_domain",
            nargs="?",
            default=None,
            help="Shop domain (e.g. moioplatform.myshopify.com). Optional if --tenant and --instance-id are set.",
        )
        parser.add_argument(
            "--tenant",
            type=int,
            default=None,
            help="Tenant ID (use with --instance-id to test the same path as sync tasks).",
        )
        parser.add_argument(
            "--instance-id",
            type=str,
            default=None,
            help="Instance ID (e.g. moioplatform). Use with --tenant.",
        )
        parser.add_argument(
            "--no-products",
            action="store_true",
            help="Only call shop.json, do not call products.json.",
        )
        parser.add_argument(
            "--no-inventory",
            action="store_true",
            help="Do not call inventory_levels.json (requires read_inventory scope).",
        )

    def handle(self, *args, **options) -> None:
        shop_domain = (options.get("shop_domain") or "").strip() or None
        tenant_id = options.get("tenant")
        instance_id = (options.get("instance_id") or "").strip() or None
        call_products = not options.get("no_products", False)
        call_inventory = not options.get("no_inventory", False)

        if shop_domain and (tenant_id is not None or instance_id):
            self.stdout.write(self.style.WARNING("Using shop_domain (ignoring --tenant/--instance-id)."))
            tenant_id = None
            instance_id = None
        if not shop_domain and (tenant_id is None or not instance_id):
            self.stderr.write("Provide either shop_domain or both --tenant and --instance-id.")
            return

        if shop_domain:
            self.stdout.write(f"Testing token for shop_domain={shop_domain} (from ShopifyShopInstallation)...")
        else:
            self.stdout.write(f"Testing token for tenant_id={tenant_id} instance_id={instance_id} (get_shopify_config_for_sync)...")

        result = test_stored_token_against_shopify(
            shop_domain=shop_domain,
            tenant_id=tenant_id,
            instance_id=instance_id,
            call_products=call_products,
            call_inventory=call_inventory,
        )

        if result["ok"]:
            self.stdout.write(self.style.SUCCESS("OK: Token is valid."))
            if result.get("shop_info"):
                self.stdout.write("Shop: " + json.dumps(result["shop_info"], indent=2))
            if result.get("products_preview") is not None:
                self.stdout.write(f"Products (limit 1): {len(result['products_preview'])} item(s)")
            if result.get("inventory_preview") is not None:
                self.stdout.write(f"Inventory levels (limit 1): {len(result['inventory_preview'])} item(s)")
        else:
            self.stdout.write(self.style.ERROR(f"FAIL: {result.get('error', 'Unknown error')}"))
            if result.get("status_code") is not None:
                self.stdout.write(f"HTTP status: {result['status_code']}")
