"""
Shopify Integration Models

Django models for Shopify data synchronization.
These models link Shopify entities to local CRM models.

The sync models (ShopifyProduct, ShopifyCustomer, ShopifyOrder, ShopifySyncLog)
live in the crm app so their migrations run on tenant schemas only.
They are re-exported here for backward compatibility.
"""

from crm.shopify_sync_models import (
    ShopifyCustomer,
    ShopifyOrder,
    ShopifyProduct,
    ShopifySyncLog,
)

__all__ = [
    "ShopifyCustomer",
    "ShopifyOrder",
    "ShopifyProduct",
    "ShopifySyncLog",
]
