"""
Shopify Integration Tasks

Celery tasks for Shopify synchronization.
Handles scheduled and real-time data sync from Shopify to CRM.
"""

import logging

from celery import shared_task
from django.conf import settings

from tenancy.models import Tenant

logger = logging.getLogger(__name__)


@shared_task(bind=True, queue=settings.MEDIUM_PRIORITY_Q)
def sync_shopify_products(self, tenant_id: int, instance_id: str = "default"):
    """
    Sync products FROM Shopify INTO CRM for a specific tenant and integration instance.

    This task receives product data from Shopify (source of truth) and updates CRM tables.
    """
    task_id = current_task.request.id
    q_name = self.request.delivery_info['routing_key']
    logger.info(f'Syncing Shopify products ---> {task_id} from {q_name}')

    try:
        from central_hub.integrations.models import IntegrationConfig
        from .service import ShopifySyncService

        tenant = Tenant.objects.get(id=tenant_id)
        config_obj = IntegrationConfig.get_for_tenant(tenant, 'shopify', instance_id)

        if not config_obj or not config_obj.enabled:
            logger.info(f"Shopify integration not enabled for tenant {tenant_id}")
            return {"status": "skipped", "reason": "integration_disabled"}

        if not config_obj.is_configured():
            logger.error(f"Shopify integration not configured for tenant {tenant_id}")
            return {"status": "failed", "reason": "not_configured"}

        # Get the last synced ID from metadata
        last_product_id = config_obj.metadata.get('last_product_id')

        sync_service = ShopifySyncService(tenant, config_obj.config)
        results = sync_service.sync_products(since_id=last_product_id)

        # Update metadata with last synced ID
        if results['last_id']:
            config_obj.metadata['last_product_id'] = results['last_id']
            config_obj.save()

        logger.info(f"Shopify products sync completed: {results}")
        return {"status": "completed", "results": results}

    except Exception as e:
        logger.exception(f"Shopify products sync failed for tenant {tenant_id}")
        return {"status": "failed", "error": str(e)}


@shared_task(bind=True, queue=settings.MEDIUM_PRIORITY_Q)
def sync_shopify_customers(self, tenant_id: int, instance_id: str = "default"):
    """
    Sync customers FROM Shopify INTO CRM for a specific tenant and integration instance.

    This task receives customer data from Shopify (source of truth) and updates CRM tables.
    """
    task_id = current_task.request.id
    q_name = self.request.delivery_info['routing_key']
    logger.info(f'Syncing Shopify customers ---> {task_id} from {q_name}')

    try:
        from central_hub.integrations.models import IntegrationConfig
        from .service import ShopifySyncService

        tenant = Tenant.objects.get(id=tenant_id)
        config_obj = IntegrationConfig.get_for_tenant(tenant, 'shopify', instance_id)

        if not config_obj or not config_obj.enabled:
            logger.info(f"Shopify integration not enabled for tenant {tenant_id}")
            return {"status": "skipped", "reason": "integration_disabled"}

        if not config_obj.is_configured():
            logger.error(f"Shopify integration not configured for tenant {tenant_id}")
            return {"status": "failed", "reason": "not_configured"}

        # Get the last synced ID from metadata
        last_customer_id = config_obj.metadata.get('last_customer_id')

        sync_service = ShopifySyncService(tenant, config_obj.config)
        results = sync_service.sync_customers(since_id=last_customer_id)

        # Update metadata with last synced ID
        if results['last_id']:
            config_obj.metadata['last_customer_id'] = results['last_id']
            config_obj.save()

        logger.info(f"Shopify customers sync completed: {results}")
        return {"status": "completed", "results": results}

    except Exception as e:
        logger.exception(f"Shopify customers sync failed for tenant {tenant_id}")
        return {"status": "failed", "error": str(e)}


@shared_task(bind=True, queue=settings.MEDIUM_PRIORITY_Q)
def sync_shopify_orders(self, tenant_id: int, instance_id: str = "default", status_filter: str = None):
    """
    Sync orders FROM Shopify INTO CRM for a specific tenant and integration instance.

    This task receives order data from Shopify (source of truth) and updates CRM tables.
    """
    task_id = current_task.request.id
    q_name = self.request.delivery_info['routing_key']
    logger.info(f'Syncing Shopify orders ---> {task_id} from {q_name}')

    try:
        from central_hub.integrations.models import IntegrationConfig
        from .service import ShopifySyncService

        tenant = Tenant.objects.get(id=tenant_id)
        config_obj = IntegrationConfig.get_for_tenant(tenant, 'shopify', instance_id)

        if not config_obj or not config_obj.enabled:
            logger.info(f"Shopify integration not enabled for tenant {tenant_id}")
            return {"status": "skipped", "reason": "integration_disabled"}

        if not config_obj.is_configured():
            logger.error(f"Shopify integration not configured for tenant {tenant_id}")
            return {"status": "failed", "reason": "not_configured"}

        # Get the last synced ID from metadata
        last_order_id = config_obj.metadata.get('last_order_id')

        sync_service = ShopifySyncService(tenant, config_obj.config)
        results = sync_service.sync_orders(since_id=last_order_id, status=status_filter)

        # Update metadata with last synced ID
        if results['last_id']:
            config_obj.metadata['last_order_id'] = results['last_id']
            config_obj.save()

        logger.info(f"Shopify orders sync completed: {results}")
        return {"status": "completed", "results": results}

    except Exception as e:
        logger.exception(f"Shopify orders sync failed for tenant {tenant_id}")
        return {"status": "failed", "error": str(e)}


@shared_task(bind=True, queue=settings.MEDIUM_PRIORITY_Q)
def sync_all_shopify_data(self, tenant_id: int, instance_id: str = "default"):
    """
    Sync all enabled Shopify data types for a tenant.

    Only syncs data types that are enabled in the Shopify integration configuration.
    Uses Shopify as the source of truth and receives data into CRM tables.
    """
    task_id = current_task.request.id
    q_name = self.request.delivery_info['routing_key']
    logger.info(f'Syncing all enabled Shopify data (receiving from Shopify) ---> {task_id} from {q_name}')

    try:
        from central_hub.integrations.models import IntegrationConfig
        from .service import ShopifySyncService

        tenant = Tenant.objects.get(id=tenant_id)
        config_obj = IntegrationConfig.get_for_tenant(tenant, 'shopify', instance_id)

        if not config_obj or not config_obj.enabled:
            logger.info(f"Shopify integration not enabled for tenant {tenant_id}")
            return {"status": "skipped", "reason": "integration_disabled"}

        if not config_obj.is_configured():
            logger.error(f"Shopify integration not configured for tenant {tenant_id}")
            return {"status": "failed", "reason": "not_configured"}

        # Check direction - this task only handles receiving
        if config_obj.config.get('direction') == 'send':
            logger.info(f"Shopify integration configured for sending, not receiving for tenant {tenant_id}")
            return {"status": "skipped", "reason": "direction_send_not_receive"}

        sync_service = ShopifySyncService(tenant, config_obj.config)
        results = sync_service.sync_all_enabled_data()

        logger.info(f"All enabled Shopify data sync completed for tenant {tenant_id}: {results}")
        return {"status": "completed", "results": results}

    except Exception as e:
        logger.exception(f"All Shopify data sync failed for tenant {tenant_id}")
        return {"status": "failed", "error": str(e)}


@shared_task(bind=True, queue=settings.MEDIUM_PRIORITY_Q)
def process_shopify_webhook(self, payload: dict, headers: dict, tenant_code: str, topic: str):
    """
    Process incoming Shopify webhook.

    Args:
        payload: Webhook payload data
        headers: Webhook headers
        tenant_code: Tenant code for identifying tenant
        topic: Webhook topic (e.g., 'products/create', 'orders/create')
    """
    task_id = current_task.request.id
    q_name = self.request.delivery_info['routing_key']
    logger.info(f'Processing Shopify webhook {topic} ---> {task_id} from {q_name}')

    try:
        from .service import ShopifySyncService
        from central_hub.integrations.models import IntegrationConfig

        tenant = Tenant.objects.get(tenant_code=tenant_code)

        # Find enabled Shopify integration for this tenant
        shopify_configs = IntegrationConfig.get_enabled_for_tenant(tenant, 'shopify')
        if not shopify_configs:
            logger.warning(f"No enabled Shopify integration found for tenant {tenant_code}")
            return {"status": "skipped", "reason": "no_integration"}

        # Use the first enabled config (assuming single shop per tenant for now)
        config_obj = shopify_configs.first()

        sync_service = ShopifySyncService(tenant, config_obj.config)

        # Process based on topic
        if topic == 'products/create' or topic == 'products/update':
            result = sync_service._sync_single_product(payload)
            return {"status": "processed", "type": "product", "action": result['action']}

        elif topic == 'customers/create' or topic == 'customers/update':
            result = sync_service._sync_single_customer(payload)
            return {"status": "processed", "type": "customer", "action": result['action']}

        elif topic == 'orders/create' or topic == 'orders/update':
            result = sync_service._sync_single_order(payload)
            return {"status": "processed", "type": "order", "action": result['action']}

        else:
            logger.info(f"Unhandled webhook topic: {topic}")
            return {"status": "ignored", "reason": f"unhandled_topic_{topic}"}

    except Exception as e:
        logger.exception(f"Shopify webhook processing failed: {e}")
        return {"status": "failed", "error": str(e)}