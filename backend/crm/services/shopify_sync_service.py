"""
Shopify Synchronization Service - RECEIVE FROM SHOPIFY

This module handles RECEIVING data from Shopify into the CRM system.

DATA FLOW: Shopify → CRM (Shopify is the source of truth)

This integration treats Shopify as the authoritative source for:
- Products (catalog, pricing, inventory)
- Customers (contact info, addresses)
- Orders (transactions, fulfillment status)

The service pulls data FROM Shopify and updates local CRM models.
It does NOT push data back to Shopify.

Configuration Options:
- direction: Must be "receive" (this service doesn't support "send")
- receive_products: Enable/disable product synchronization
- receive_customers: Enable/disable customer synchronization
- receive_orders: Enable/disable order synchronization
- receive_inventory: Enable/disable inventory synchronization

Usage:
    config = {
        "direction": "receive",
        "store_url": "mystore.myshopify.com",
        "access_token": "shopify_token",
        "receive_products": True,
        "receive_customers": True,
        "receive_orders": True,
    }
    service = ShopifySyncService(tenant, config)
    results = service.sync_all_enabled_data()
"""

import logging
from typing import Dict, List, Optional, Tuple

from django.db import transaction
from django.utils import timezone

from crm.lib.shopify_api import ShopifyAPIClient, parse_shopify_timestamp
from crm.models import (
    Product,
    Customer,
    EcommerceOrder,
    EcommerceOrderLine,
    ShopifyProduct,
    ShopifyCustomer,
    ShopifyOrder,
    ShopifySyncLog,
    Tag,
    Tenant,
)
from tenancy.models import Tenant

logger = logging.getLogger(__name__)


class ShopifySyncService:
    """
    Shopify Synchronization Service - RECEIVE ONLY

    This service is designed exclusively for RECEIVING data from Shopify as the source of truth.
    It pulls data from Shopify and updates local CRM models accordingly.

    IMPORTANT: This service does NOT send data back to Shopify. For bidirectional sync
    or sending data to Shopify, use a different service or extend this one.

    Data Flow: Shopify → CRM (Shopify is the authoritative source)
    """

    def __init__(self, tenant: Tenant, shopify_config: Dict):
        """
        Initialize sync service.

        Args:
            tenant: Tenant instance
            shopify_config: Shopify integration config dict
        """
        self.tenant = tenant
        self.config = shopify_config

        # Validate direction - this service only handles receiving from Shopify
        direction = shopify_config.get('direction', 'receive')
        if direction == 'send':
            raise ValueError(
                "This ShopifySyncService only handles RECEIVING data from Shopify. "
                "For sending data TO Shopify, use a different service or configure direction='receive'. "
                "Current config has direction='send' which is not supported by this service."
            )
        elif direction != 'receive':
            logger.warning(f"Unknown direction '{direction}', defaulting to 'receive'")

        self.api_client = ShopifyAPIClient(
            store_url=shopify_config.get('store_url', ''),
            access_token=shopify_config.get('access_token', ''),
            api_version=shopify_config.get('api_version', '2024-01'),
        )

        # Extract receive flags
        self.receive_products = shopify_config.get('receive_products', True)
        self.receive_customers = shopify_config.get('receive_customers', True)
        self.receive_orders = shopify_config.get('receive_orders', True)
        self.receive_inventory = shopify_config.get('receive_inventory', True)

    def sync_products(self, since_id: Optional[str] = None) -> Dict:
        """
        Sync products from Shopify into CRM.

        Only runs if receive_products is enabled in configuration.

        Args:
            since_id: Only sync products with ID greater than this

        Returns:
            Dict with sync results
        """
        if not self.receive_products:
            return {"skipped": True, "reason": "receive_products_disabled"}

        sync_log = ShopifySyncLog.objects.create(
            tenant=self.tenant,
            sync_type='products',
            shopify_shop_domain=self.config.get('store_url', ''),
        )

        try:
            # Get products from Shopify
            params = {'limit': 250}
            if since_id:
                params['since_id'] = since_id

            shopify_products = self.api_client.get_products(params=params)

            results = {
                'processed': 0,
                'created': 0,
                'updated': 0,
                'failed': 0,
                'last_id': None,
            }

            for shopify_product in shopify_products:
                try:
                    with transaction.atomic():
                        result = self._sync_single_product(shopify_product)
                        if result['action'] == 'created':
                            results['created'] += 1
                        elif result['action'] == 'updated':
                            results['updated'] += 1
                        results['processed'] += 1
                        results['last_id'] = shopify_product['id']

                except Exception as e:
                    logger.error(f"Failed to sync product {shopify_product.get('id')}: {e}")
                    results['failed'] += 1

            sync_log.mark_completed(**results)
            return results

        except Exception as e:
            logger.error(f"Product sync failed: {e}")
            sync_log.mark_failed(str(e))
            raise

    def sync_customers(self, since_id: Optional[str] = None) -> Dict:
        """
        Sync customers from Shopify into CRM.

        Only runs if receive_customers is enabled in configuration.

        Args:
            since_id: Only sync customers with ID greater than this

        Returns:
            Dict with sync results
        """
        if not self.receive_customers:
            return {"skipped": True, "reason": "receive_customers_disabled"}

        sync_log = ShopifySyncLog.objects.create(
            tenant=self.tenant,
            sync_type='customers',
            shopify_shop_domain=self.config.get('store_url', ''),
        )

        try:
            # Get customers from Shopify
            params = {'limit': 250}
            if since_id:
                params['since_id'] = since_id

            shopify_customers = self.api_client.get_customers(params=params)

            results = {
                'processed': 0,
                'created': 0,
                'updated': 0,
                'failed': 0,
                'last_id': None,
            }

            for shopify_customer in shopify_customers:
                try:
                    with transaction.atomic():
                        result = self._sync_single_customer(shopify_customer)
                        if result['action'] == 'created':
                            results['created'] += 1
                        elif result['action'] == 'updated':
                            results['updated'] += 1
                        results['processed'] += 1
                        results['last_id'] = shopify_customer['id']

                except Exception as e:
                    logger.error(f"Failed to sync customer {shopify_customer.get('id')}: {e}")
                    results['failed'] += 1

            sync_log.mark_completed(**results)
            return results

        except Exception as e:
            logger.error(f"Customer sync failed: {e}")
            sync_log.mark_failed(str(e))
            raise

    def sync_orders(self, since_id: Optional[str] = None, status: Optional[str] = None) -> Dict:
        """
        Sync orders from Shopify into CRM.

        Only runs if receive_orders is enabled in configuration.

        Args:
            since_id: Only sync orders with ID greater than this
            status: Filter by order status (any, open, closed, cancelled)

        Returns:
            Dict with sync results
        """
        if not self.receive_orders:
            return {"skipped": True, "reason": "receive_orders_disabled"}

        sync_log = ShopifySyncLog.objects.create(
            tenant=self.tenant,
            sync_type='orders',
            shopify_shop_domain=self.config.get('store_url', ''),
        )

        try:
            # Get orders from Shopify
            params = {'limit': 250}
            if since_id:
                params['since_id'] = since_id
            if status:
                params['status'] = status

            shopify_orders = self.api_client.get_orders(params=params)

            results = {
                'processed': 0,
                'created': 0,
                'updated': 0,
                'failed': 0,
                'last_id': None,
            }

            for shopify_order in shopify_orders:
                try:
                    with transaction.atomic():
                        result = self._sync_single_order(shopify_order)
                        if result['action'] == 'created':
                            results['created'] += 1
                        elif result['action'] == 'updated':
                            results['updated'] += 1
                        results['processed'] += 1
                        results['last_id'] = shopify_order['id']

                except Exception as e:
                    logger.error(f"Failed to sync order {shopify_order.get('id')}: {e}")
                    results['failed'] += 1

            sync_log.mark_completed(**results)
            return results

        except Exception as e:
            logger.error(f"Order sync failed: {e}")
            sync_log.mark_failed(str(e))
            raise

    def get_sync_configuration_summary(self) -> Dict:
        """
        Get a summary of what data will be synced based on configuration.

        Returns:
            Dict with configuration summary
        """
        return {
            "direction": "receive_from_shopify",
            "description": "Shopify is the source of truth - receiving data into CRM",
            "enabled_syncs": {
                "products": self.receive_products,
                "customers": self.receive_customers,
                "orders": self.receive_orders,
                "inventory": self.receive_inventory,
            },
            "store_url": self.config.get('store_url'),
            "api_version": self.config.get('api_version', '2024-01'),
        }

    def sync_all_enabled_data(self) -> Dict:
        """
        Sync all enabled data types from Shopify into CRM.

        Only syncs data types that are enabled in the configuration.
        This method treats Shopify as the source of truth.

        Returns:
            Dict with sync results for each data type
        """
        results = {
            "products": None,
            "customers": None,
            "orders": None,
        }

        # Sync products if enabled
        if self.receive_products:
            try:
                results["products"] = self.sync_products()
            except Exception as e:
                logger.error(f"Product sync failed: {e}")
                results["products"] = {"status": "failed", "error": str(e)}

        # Sync customers if enabled
        if self.receive_customers:
            try:
                results["customers"] = self.sync_customers()
            except Exception as e:
                logger.error(f"Customer sync failed: {e}")
                results["customers"] = {"status": "failed", "error": str(e)}

        # Sync orders if enabled
        if self.receive_orders:
            try:
                results["orders"] = self.sync_orders()
            except Exception as e:
                logger.error(f"Order sync failed: {e}")
                results["orders"] = {"status": "failed", "error": str(e)}

        return results

    def _sync_single_product(self, shopify_product: Dict) -> Dict:
        """
        Sync a single Shopify product.

        Returns dict with 'action' ('created' or 'updated') and product instance.
        """
        shopify_id = str(shopify_product['id'])

        # Check if we already have this product
        shopify_product_obj, created = ShopifyProduct.objects.get_or_create(
            shopify_id=shopify_id,
            defaults={'tenant': self.tenant}
        )

        # Create or update local Product
        if shopify_product_obj.product:
            # Update existing product
            product = shopify_product_obj.product
            action = 'updated'
        else:
            # Create new product
            product = Product(tenant=self.tenant)
            action = 'created'

        # Update product fields
        product.name = shopify_product.get('title', '')
        product.description = shopify_product.get('body_html', '')

        # Get price from first variant
        variants = shopify_product.get('variants', [])
        if variants:
            variant = variants[0]
            product.price = float(variant.get('price', 0))
            product.sale_price = float(variant.get('compare_at_price', 0) or variant.get('price', 0))
            product.sku = variant.get('sku')

        product.main_image = self._extract_main_image(shopify_product)
        product.permalink = f"https://{self.config.get('store_url')}/products/{shopify_product.get('handle')}"

        # Handle product attributes
        attributes = {}
        if variants:
            variant = variants[0]
            attributes.update({
                'weight': variant.get('weight'),
                'weight_unit': variant.get('weight_unit'),
                'inventory_quantity': variant.get('inventory_quantity'),
            })

        # Add options as attributes
        options = shopify_product.get('options', [])
        for option in options:
            if option.get('name') and option.get('values'):
                attributes[option['name']] = option['values']

        product.attributes = attributes
        product.save()

        # Update ShopifyProduct fields
        shopify_product_obj.product = product
        shopify_product_obj.handle = shopify_product.get('handle', '')
        shopify_product_obj.product_type = shopify_product.get('product_type', '')
        shopify_product_obj.vendor = shopify_product.get('vendor', '')
        shopify_product_obj.tags = shopify_product.get('tags', '').split(', ') if shopify_product.get('tags') else []

        # Parse timestamps
        if shopify_product.get('published_at'):
            shopify_product_obj.published_at = parse_shopify_timestamp(shopify_product['published_at'])
        if shopify_product.get('created_at'):
            shopify_product_obj.created_at_shopify = parse_shopify_timestamp(shopify_product['created_at'])
        if shopify_product.get('updated_at'):
            shopify_product_obj.updated_at_shopify = parse_shopify_timestamp(shopify_product['updated_at'])

        shopify_product_obj.sync_status = shopify_product.get('status', 'active')
        shopify_product_obj.last_synced = timezone.now()
        shopify_product_obj.save()

        # Handle tags
        self._sync_product_tags(product, shopify_product_obj.tags)

        return {'action': action, 'product': product}

    def _sync_single_customer(self, shopify_customer: Dict) -> Dict:
        """
        Sync a single Shopify customer.

        Returns dict with 'action' ('created' or 'updated') and customer instance.
        """
        shopify_id = str(shopify_customer['id'])

        # Check if we already have this customer
        shopify_customer_obj, created = ShopifyCustomer.objects.get_or_create(
            shopify_id=shopify_id,
            defaults={'tenant': self.tenant}
        )

        # Create or update local Customer
        if shopify_customer_obj.customer:
            # Update existing customer
            customer = shopify_customer_obj.customer
            action = 'updated'
        else:
            # Create new customer
            customer = Customer(tenant=self.tenant)
            action = 'created'

        # Update customer fields
        customer.first_name = shopify_customer.get('first_name', '')
        customer.last_name = shopify_customer.get('last_name', '')
        customer.name = f"{customer.first_name} {customer.last_name}".strip() or shopify_customer.get('email', '')
        customer.email = shopify_customer.get('email')
        customer.phone = shopify_customer.get('phone')

        # Handle external_id for linking
        if customer.external_id is None:
            customer.external_id = f"shopify:{shopify_id}"

        customer.save()

        # Update ShopifyCustomer fields
        shopify_customer_obj.customer = customer
        shopify_customer_obj.email = shopify_customer.get('email', '')
        shopify_customer_obj.first_name = shopify_customer.get('first_name', '')
        shopify_customer_obj.last_name = shopify_customer.get('last_name', '')
        shopify_customer_obj.phone = shopify_customer.get('phone', '')
        shopify_customer_obj.verified_email = shopify_customer.get('verified_email', False)
        shopify_customer_obj.accepts_marketing = shopify_customer.get('accepts_marketing', False)
        shopify_customer_obj.tax_exempt = shopify_customer.get('tax_exempt', False)
        shopify_customer_obj.tags = shopify_customer.get('tags', '').split(', ') if shopify_customer.get('tags') else []

        # Address data
        addresses = shopify_customer.get('addresses', [])
        shopify_customer_obj.addresses = addresses
        if addresses:
            shopify_customer_obj.default_address = addresses[0]  # First address as default

        # Parse timestamps
        if shopify_customer.get('created_at'):
            shopify_customer_obj.created_at_shopify = parse_shopify_timestamp(shopify_customer['created_at'])
        if shopify_customer.get('updated_at'):
            shopify_customer_obj.updated_at_shopify = parse_shopify_timestamp(shopify_customer['updated_at'])

        shopify_customer_obj.last_synced = timezone.now()
        shopify_customer_obj.save()

        # Create or update address record
        if addresses:
            self._sync_customer_address(customer, addresses[0])

        return {'action': action, 'customer': customer}

    def _sync_single_order(self, shopify_order: Dict) -> Dict:
        """
        Sync a single Shopify order.

        Returns dict with 'action' ('created' or 'updated') and order instance.
        """
        shopify_id = str(shopify_order['id'])

        # Check if we already have this order
        shopify_order_obj, created = ShopifyOrder.objects.get_or_create(
            shopify_id=shopify_id,
            defaults={'tenant': self.tenant}
        )

        # Create or update local EcommerceOrder
        if shopify_order_obj.ecommerce_order:
            # Update existing order
            order = shopify_order_obj.ecommerce_order
            action = 'updated'
        else:
            # Create new order
            order = EcommerceOrder(tenant=self.tenant)
            action = 'created'

        # Update order fields
        order.order_number = str(shopify_order.get('order_number', ''))
        order.status = self._map_order_status(shopify_order)
        order.customer_name = self._extract_customer_name(shopify_order)
        order.customer_email = shopify_order.get('email')
        order.customer_phone = shopify_order.get('phone')
        order.total = float(shopify_order.get('total_price', 0))
        order.payload = shopify_order

        # Parse timestamps
        if shopify_order.get('created_at'):
            order.created = parse_shopify_timestamp(shopify_order['created_at'])
        if shopify_order.get('updated_at'):
            order.modified = parse_shopify_timestamp(shopify_order['updated_at'])

        order.save()

        # Update ShopifyOrder fields
        shopify_order_obj.ecommerce_order = order
        shopify_order_obj.order_number = str(shopify_order.get('order_number', ''))
        shopify_order_obj.name = shopify_order.get('name', '')
        shopify_order_obj.email = shopify_order.get('email', '')
        shopify_order_obj.phone = shopify_order.get('phone', '')

        # Financial data
        shopify_order_obj.subtotal_price = float(shopify_order.get('subtotal_price', 0))
        shopify_order_obj.total_tax = float(shopify_order.get('total_tax', 0))
        shopify_order_obj.total_discounts = float(shopify_order.get('total_discounts', 0))
        shopify_order_obj.total_price = float(shopify_order.get('total_price', 0))

        # Addresses
        shopify_order_obj.shipping_address = shopify_order.get('shipping_address')
        shopify_order_obj.billing_address = shopify_order.get('billing_address')
        shopify_order_obj.shipping_lines = shopify_order.get('shipping_lines', [])

        # Order data
        shopify_order_obj.line_items = shopify_order.get('line_items', [])
        shopify_order_obj.financial_status = shopify_order.get('financial_status', '')
        shopify_order_obj.fulfillment_status = shopify_order.get('fulfillment_status', '')

        # Parse timestamps
        if shopify_order.get('created_at'):
            shopify_order_obj.created_at_shopify = parse_shopify_timestamp(shopify_order['created_at'])
        if shopify_order.get('updated_at'):
            shopify_order_obj.updated_at_shopify = parse_shopify_timestamp(shopify_order['updated_at'])
        if shopify_order.get('processed_at'):
            shopify_order_obj.processed_at = parse_shopify_timestamp(shopify_order['processed_at'])

        shopify_order_obj.last_synced = timezone.now()
        shopify_order_obj.save()

        # Sync order line items
        self._sync_order_line_items(order, shopify_order.get('line_items', []))

        return {'action': action, 'order': order}

    def _extract_main_image(self, shopify_product: Dict) -> Optional[str]:
        """Extract main product image URL from Shopify product data."""
        images = shopify_product.get('images', [])
        if images:
            return images[0].get('src')
        return None

    def _sync_product_tags(self, product: Product, shopify_tags: List[str]):
        """Sync Shopify tags to local Tag model."""
        tags = []
        for tag_name in shopify_tags:
            tag, _ = Tag.objects.get_or_create(
                name=tag_name.strip(),
                tenant=self.tenant,
                context='product',
                defaults={'slug': tag_name.lower().replace(' ', '-')}
            )
            tags.append(tag)

        product.tags.set(tags)

    def _sync_customer_address(self, customer: Customer, address_data: Dict):
        """Create or update customer address."""
        from crm.models import Address

        # Find existing address or create new one
        address, created = Address.objects.get_or_create(
            customer=customer,
            defaults={
                'name': 'Shopify Address',
                'invoice_address': True,
                'delivery_address': True,
                'enabled': True,
            }
        )

        # Update address fields
        address.address = address_data.get('address1', '')
        address.address_internal = address_data.get('address2', '')
        address.city = address_data.get('city', '')
        address.state = address_data.get('province', '')
        address.country = address_data.get('country', '')
        address.postalcode = address_data.get('zip', '')

        address.save()

    def _sync_order_line_items(self, order: EcommerceOrder, line_items: List[Dict]):
        """Sync order line items."""
        # Clear existing line items
        EcommerceOrderLine.objects.filter(order=order).delete()

        # Create new line items
        for item in line_items:
            EcommerceOrderLine.objects.create(
                order=order,
                sku=item.get('sku', ''),
                sale_price=float(item.get('price', 0)),
                order_qty=float(item.get('quantity', 0)),
                line_total=float(item.get('total', 0)),
                line_tax=float(item.get('total_tax', 0)),
            )

    def _map_order_status(self, shopify_order: Dict) -> str:
        """Map Shopify order status to local status."""
        financial_status = shopify_order.get('financial_status', '')
        fulfillment_status = shopify_order.get('fulfillment_status', '')

        # Simple mapping - can be enhanced based on business rules
        if financial_status == 'paid' and fulfillment_status == 'fulfilled':
            return 'completed'
        elif financial_status == 'paid':
            return 'processing'
        elif financial_status == 'refunded':
            return 'refunded'
        elif financial_status == 'cancelled':
            return 'cancelled'
        else:
            return 'pending'

    def _extract_customer_name(self, shopify_order: Dict) -> str:
        """Extract customer name from Shopify order."""
        billing_address = shopify_order.get('billing_address', {})
        if billing_address:
            first_name = billing_address.get('first_name', '')
            last_name = billing_address.get('last_name', '')
            if first_name or last_name:
                return f"{first_name} {last_name}".strip()

        return shopify_order.get('customer', {}).get('first_name', '') + ' ' + shopify_order.get('customer', {}).get('last_name', '').strip() or ''