"""
Shopify Webhook Handlers

Handles real-time webhooks from Shopify for instant data synchronization.
"""

import logging

from central_hub.webhooks.registry import webhook_handler

logger = logging.getLogger(__name__)


@webhook_handler("shopify_webhook")
def shopify_webhook_handler(payload, headers, content_type, cfg):
    """
    Handle Shopify webhooks for real-time data synchronization.

    Receives data from Shopify (source of truth) and syncs into CRM tables.
    Supports products, customers, and orders webhook topics.
    Routes to appropriate async processing task.
    """
    try:
        # Extract topic from headers
        topic = headers.get('X-Shopify-Topic', '')
        shop_domain = headers.get('X-Shopify-Shop-Domain', '')

        if not topic:
            logger.error("Shopify webhook missing X-Shopify-Topic header")
            return {"status": "error", "message": "Missing topic header"}

        logger.info(f"Processing Shopify webhook: topic={topic}, shop={shop_domain}")

        # Validate webhook signature if secret is configured
        # Note: Shopify webhook signature validation would go here

        # Queue async processing
        from django_celery_results.models import TaskResult
        from central_hub.integrations.shopify.tasks import process_shopify_webhook

        task = process_shopify_webhook.delay(
            payload=payload,
            headers=dict(headers),  # Convert to dict for serialization
            tenant_code=cfg.tenant.tenant_code,
            topic=topic
        )

        logger.info(f"Queued Shopify webhook processing: task_id={task.id}")

        return {
            "status": "queued",
            "task_id": task.id,
            "topic": topic,
            "shop_domain": shop_domain
        }

    except Exception as e:
        logger.exception(f"Shopify webhook handler failed: {e}")
        return {"status": "error", "message": str(e)}


@webhook_handler("shopify_product_webhook")
def shopify_product_webhook_handler(payload, headers, content_type, cfg):
    """
    Handle Shopify product webhooks (create/update/delete).

    Receives product changes from Shopify (source of truth) and syncs into CRM.
    This is a specialized handler that processes product changes immediately
    for better performance on high-volume product updates.
    """
    try:
        topic = headers.get('X-Shopify-Topic', '')

        if topic not in ['products/create', 'products/update', 'products/delete']:
            return {"status": "ignored", "reason": f"unhandled_topic_{topic}"}

        from .service import ShopifySyncService
        from central_hub.integrations.models import IntegrationConfig

        # Find enabled Shopify integration for this tenant
        shopify_configs = IntegrationConfig.get_enabled_for_tenant(cfg.tenant, 'shopify')
        if not shopify_configs:
            logger.warning(f"No enabled Shopify integration found for tenant {cfg.tenant}")
            return {"status": "skipped", "reason": "no_integration"}

        # Use the first enabled config
        config_obj = shopify_configs.first()
        sync_service = ShopifySyncService(tenant=cfg.tenant, shopify_config=config_obj.config)

        if topic == 'products/delete':
            # Handle product deletion
            from .models import ShopifyProduct
            shopify_id = str(payload.get('id', ''))
            try:
                shopify_product = ShopifyProduct.objects.get(
                    tenant=cfg.tenant,
                    shopify_id=shopify_id
                )
                if shopify_product.product:
                    # Mark as inactive instead of deleting
                    shopify_product.sync_status = 'archived'
                    shopify_product.save()
                return {"status": "processed", "action": "archived"}
            except ShopifyProduct.DoesNotExist:
                return {"status": "skipped", "reason": "product_not_found"}

        else:
            # Handle create/update
            result = sync_service._sync_single_product(payload)
            return {"status": "processed", "action": result['action']}

    except Exception as e:
        logger.exception(f"Shopify product webhook handler failed: {e}")
        return {"status": "error", "message": str(e)}


@webhook_handler("shopify_order_webhook")
def shopify_order_webhook_handler(payload, headers, content_type, cfg):
    """
    Handle Shopify order webhooks (create/update/cancelled).

    Receives order changes from Shopify (source of truth) and syncs into CRM.
    Specialized handler for order processing with priority handling.
    """
    try:
        topic = headers.get('X-Shopify-Topic', '')

        if topic not in ['orders/create', 'orders/update', 'orders/cancelled', 'orders/fulfilled']:
            return {"status": "ignored", "reason": f"unhandled_topic_{topic}"}

        from .service import ShopifySyncService
        from central_hub.integrations.models import IntegrationConfig

        # Find enabled Shopify integration for this tenant
        shopify_configs = IntegrationConfig.get_enabled_for_tenant(cfg.tenant, 'shopify')
        if not shopify_configs:
            logger.warning(f"No enabled Shopify integration found for tenant {cfg.tenant}")
            return {"status": "skipped", "reason": "no_integration"}

        # Use the first enabled config
        config_obj = shopify_configs.first()
        sync_service = ShopifySyncService(tenant=cfg.tenant, shopify_config=config_obj.config)

        result = sync_service._sync_single_order(payload)
        return {"status": "processed", "action": result['action'], "topic": topic}

    except Exception as e:
        logger.exception(f"Shopify order webhook handler failed: {e}")
        return {"status": "error", "message": str(e)}