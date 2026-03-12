"""
Shopify Integration Tasks

Celery tasks for Shopify synchronization.
Handles scheduled and real-time data sync from Shopify to CRM.
CRM models (ShopifySyncLog, ShopifyProduct, etc.) live in tenant schemas;
tasks must run sync inside tenant_schema_context so the correct tables exist.
"""

import logging

from celery import shared_task
from django.conf import settings

from tenancy.models import Tenant
from tenancy.tenant_support import tenant_schema_context

logger = logging.getLogger(__name__)


def _routing_key(task) -> str:
    return str((task.request.delivery_info or {}).get("routing_key", ""))


def _on_shopify_401(instance_id: str) -> None:
    """On 401: try token refresh if we have a refresh_token; otherwise clear state so UI shows disconnected."""
    from central_hub.integrations.models import ShopifyShopInstallation
    from central_hub.integrations.shopify.token_refresh import refresh_shopify_installation_token
    from .service import _instance_id_to_shop_domain
    from .webhook_receiver import mark_shopify_shop_uninstalled
    shop_domain = _instance_id_to_shop_domain(instance_id)
    if not shop_domain:
        return
    installation = ShopifyShopInstallation.objects.filter(shop_domain=shop_domain).first()
    if installation and (installation.refresh_token or "").strip() and refresh_shopify_installation_token(installation):
        logger.info("Sync received 401; refreshed token for shop=%s (next sync will use new token)", shop_domain)
        return
    mark_shopify_shop_uninstalled(shop_domain)
    logger.info("Sync received 401; cleared Shopify state for shop=%s (re-install from Shopify to reconnect)", shop_domain)


@shared_task(
    bind=True,
    name="central_hub.integrations.shopify.tasks.sync_shopify_products",
    queue=settings.MEDIUM_PRIORITY_Q,
)
def sync_shopify_products(self, tenant_id: int, instance_id: str = "default"):
    """
    Sync products FROM Shopify INTO CRM for a specific tenant and integration instance.

    This task receives product data from Shopify (source of truth) and updates CRM tables.
    """
    task_id = self.request.id
    q_name = _routing_key(self)
    logger.info('Syncing Shopify products tenant_id=%s instance_id=%s task_id=%s', tenant_id, instance_id, task_id)

    try:
        from central_hub.integrations.models import IntegrationConfig
        from .service import ShopifySyncService, get_shopify_config_for_sync

        tenant = Tenant.objects.get(id=tenant_id)
        config = get_shopify_config_for_sync(tenant_id, instance_id)
        if not config:
            logger.info(f"Shopify integration not enabled or not configured for tenant {tenant_id} instance {instance_id}")
            return {"status": "skipped", "reason": "integration_disabled"}

        config_obj = IntegrationConfig.get_for_tenant(tenant, "shopify", instance_id)
        last_product_id = (config_obj.metadata or {}).get("last_product_id") if config_obj else None

        schema_name = getattr(tenant, "schema_name", None)
        with tenant_schema_context(schema_name):
            sync_service = ShopifySyncService(tenant, config)
            results = sync_service.sync_products(since_id=last_product_id)

        if config_obj and results.get("last_id"):
            config_obj.metadata = config_obj.metadata or {}
            config_obj.metadata["last_product_id"] = results["last_id"]
            config_obj.save(update_fields=["metadata", "updated_at"])

        logger.info(f"Shopify products sync completed: {results}")
        return {"status": "completed", "results": results}

    except Exception as e:
        from central_hub.integrations.shopify.shopify_api import ShopifyAPIError
        if isinstance(e, ShopifyAPIError) and "401" in str(e):
            _on_shopify_401(instance_id)
        logger.exception(f"Shopify products sync failed for tenant {tenant_id}")
        return {"status": "failed", "error": str(e)}


@shared_task(
    bind=True,
    name="central_hub.integrations.shopify.tasks.sync_shopify_customers",
    queue=settings.MEDIUM_PRIORITY_Q,
)
def sync_shopify_customers(self, tenant_id: int, instance_id: str = "default"):
    """
    Sync customers FROM Shopify INTO CRM for a specific tenant and integration instance.

    This task receives customer data from Shopify (source of truth) and updates CRM tables.
    """
    task_id = self.request.id
    q_name = _routing_key(self)
    logger.info(f'Syncing Shopify customers ---> {task_id} from {q_name}')

    try:
        from central_hub.integrations.models import IntegrationConfig
        from .service import ShopifySyncService, get_shopify_config_for_sync

        tenant = Tenant.objects.get(id=tenant_id)
        config = get_shopify_config_for_sync(tenant_id, instance_id)
        if not config:
            logger.info(f"Shopify integration not enabled or not configured for tenant {tenant_id} instance {instance_id}")
            return {"status": "skipped", "reason": "integration_disabled"}

        config_obj = IntegrationConfig.get_for_tenant(tenant, "shopify", instance_id)
        last_customer_id = (config_obj.metadata or {}).get("last_customer_id") if config_obj else None

        schema_name = getattr(tenant, "schema_name", None)
        with tenant_schema_context(schema_name):
            sync_service = ShopifySyncService(tenant, config)
            results = sync_service.sync_customers(since_id=last_customer_id)

        if config_obj and results.get("last_id"):
            config_obj.metadata = config_obj.metadata or {}
            config_obj.metadata["last_customer_id"] = results["last_id"]
            config_obj.save(update_fields=["metadata", "updated_at"])

        logger.info(f"Shopify customers sync completed: {results}")
        return {"status": "completed", "results": results}

    except Exception as e:
        from central_hub.integrations.shopify.shopify_api import ShopifyAPIError
        if isinstance(e, ShopifyAPIError) and "401" in str(e):
            _on_shopify_401(instance_id)
        logger.exception(f"Shopify customers sync failed for tenant {tenant_id}")
        return {"status": "failed", "error": str(e)}


@shared_task(
    bind=True,
    name="central_hub.integrations.shopify.tasks.sync_shopify_orders",
    queue=settings.MEDIUM_PRIORITY_Q,
)
def sync_shopify_orders(self, tenant_id: int, instance_id: str = "default", status_filter: str = None):
    """
    Sync orders FROM Shopify INTO CRM for a specific tenant and integration instance.

    This task receives order data from Shopify (source of truth) and updates CRM tables.
    """
    task_id = self.request.id
    q_name = _routing_key(self)
    logger.info(f'Syncing Shopify orders ---> {task_id} from {q_name}')

    try:
        from central_hub.integrations.models import IntegrationConfig
        from .service import ShopifySyncService, get_shopify_config_for_sync

        tenant = Tenant.objects.get(id=tenant_id)
        config = get_shopify_config_for_sync(tenant_id, instance_id)
        if not config:
            logger.info(f"Shopify integration not enabled or not configured for tenant {tenant_id} instance {instance_id}")
            return {"status": "skipped", "reason": "integration_disabled"}

        config_obj = IntegrationConfig.get_for_tenant(tenant, "shopify", instance_id)
        last_order_id = (config_obj.metadata or {}).get("last_order_id") if config_obj else None

        schema_name = getattr(tenant, "schema_name", None)
        with tenant_schema_context(schema_name):
            sync_service = ShopifySyncService(tenant, config)
            results = sync_service.sync_orders(since_id=last_order_id, status=status_filter)

        if config_obj and results.get("last_id"):
            config_obj.metadata = config_obj.metadata or {}
            config_obj.metadata["last_order_id"] = results["last_id"]
            config_obj.save(update_fields=["metadata", "updated_at"])

        logger.info(f"Shopify orders sync completed: {results}")
        return {"status": "completed", "results": results}

    except Exception as e:
        from central_hub.integrations.shopify.shopify_api import ShopifyAPIError
        if isinstance(e, ShopifyAPIError) and "401" in str(e):
            _on_shopify_401(instance_id)
        logger.exception(f"Shopify orders sync failed for tenant {tenant_id}")
        return {"status": "failed", "error": str(e)}


@shared_task(
    bind=True,
    name="central_hub.integrations.shopify.tasks.sync_all_shopify_data",
    queue=settings.MEDIUM_PRIORITY_Q,
)
def sync_all_shopify_data(self, tenant_id: int, instance_id: str = "default"):
    """
    Sync all enabled Shopify data types for a tenant.

    Only syncs data types that are enabled in the Shopify integration configuration.
    Uses Shopify as the source of truth and receives data into CRM tables.
    """
    task_id = self.request.id
    q_name = _routing_key(self)
    logger.info(
        "Syncing all enabled Shopify data (receiving from Shopify) tenant_id=%s instance_id=%s ---> %s from %s",
        tenant_id, instance_id, task_id, q_name,
    )

    try:
        from central_hub.integrations.models import IntegrationConfig
        from .service import ShopifySyncService, get_shopify_config_for_sync

        tenant = Tenant.objects.get(id=tenant_id)
        config = get_shopify_config_for_sync(tenant_id, instance_id)
        if not config:
            logger.info(f"Shopify integration not enabled or not configured for tenant {tenant_id} instance {instance_id}")
            return {"status": "skipped", "reason": "integration_disabled"}

        if config.get("direction") == "send":
            logger.info(f"Shopify integration configured for sending, not receiving for tenant {tenant_id}")
            return {"status": "skipped", "reason": "direction_send_not_receive"}

        schema_name = getattr(tenant, "schema_name", None)
        with tenant_schema_context(schema_name):
            sync_service = ShopifySyncService(tenant, config)
            results = sync_service.sync_all_enabled_data()

        # sync_all_enabled_data catches exceptions and returns { status: "failed", error: "..." };
        # so we must detect 401 from results and clear state (otherwise we never call _on_shopify_401)
        def _result_has_401(res):
            if not res or not isinstance(res, dict):
                return False
            return "401" in str(res.get("error") or "")
        if any(_result_has_401(results.get(k)) for k in ("products", "customers", "orders")):
            logger.warning(
                "Sync result contained 401; running 401 cleanup for instance_id=%s tenant_id=%s",
                instance_id, tenant_id,
            )
            _on_shopify_401(instance_id)

        logger.info(
            "All enabled Shopify data sync completed for tenant %s instance_id=%s: %s",
            tenant_id, instance_id, results,
        )
        return {"status": "completed", "results": results}

    except Exception as e:
        from central_hub.integrations.shopify.shopify_api import ShopifyAPIError
        if isinstance(e, ShopifyAPIError) and "401" in str(e):
            _on_shopify_401(instance_id)
        logger.exception(f"All Shopify data sync failed for tenant {tenant_id}")
        return {"status": "failed", "error": str(e)}


@shared_task(
    bind=True,
    name="central_hub.integrations.shopify.tasks.test_shopify_connection",
    queue=settings.MEDIUM_PRIORITY_Q,
)
def test_shopify_connection(
    self,
    tenant_id: int,
    instance_id: str = "default",
    call_products: bool = True,
    call_customers: bool = False,
    call_orders: bool = False,
    call_inventory: bool = True,
):
    """
    Test Shopify API access only – no sync, no CRM writes.

    Makes lightweight limit=1 API calls for each requested resource
    to verify the stored token works and the scope covers them.
    """
    task_id = self.request.id
    logger.info("test_shopify_connection tenant_id=%s instance_id=%s task_id=%s checks=products:%s,customers:%s,orders:%s,inventory:%s",
                tenant_id, instance_id, task_id, call_products, call_customers, call_orders, call_inventory)

    from .service import test_stored_token_against_shopify

    result = test_stored_token_against_shopify(
        tenant_id=tenant_id,
        instance_id=instance_id,
        call_products=call_products,
        call_customers=call_customers,
        call_orders=call_orders,
        call_inventory=call_inventory,
    )
    if result.get("ok"):
        return {"status": "ok", "shop_info": result.get("shop_info"), "test_result": result}
    return {
        "status": "failed",
        "error": result.get("error"),
        "status_code": result.get("status_code"),
        "test_result": result,
    }


@shared_task(
    bind=True,
    name="central_hub.integrations.shopify.tasks.process_shopify_webhook",
    queue=settings.MEDIUM_PRIORITY_Q,
)
def process_shopify_webhook(self, payload: dict, headers: dict, tenant_code: str, topic: str):
    """
    Process incoming Shopify webhook.

    Args:
        payload: Webhook payload data
        headers: Webhook headers
        tenant_code: Tenant code for identifying tenant
        topic: Webhook topic (e.g., 'products/create', 'orders/create')
    """
    task_id = self.request.id
    q_name = _routing_key(self)
    logger.info(f'Processing Shopify webhook {topic} ---> {task_id} from {q_name}')

    try:
        from .service import ShopifySyncService, get_shopify_config_for_sync
        from central_hub.integrations.models import IntegrationConfig, ShopifyShopLink, ShopifyShopLinkStatus

        # Resolve tenant and instance_id from shop_domain (Hub: canonical shop identity)
        shop_domain = (headers.get("X-Shopify-Shop-Domain") or "").strip()
        if not shop_domain:
            tenant = Tenant.objects.get(tenant_code=tenant_code)
            shopify_configs = IntegrationConfig.get_enabled_for_tenant(tenant, "shopify")
            config_obj = shopify_configs.first() if shopify_configs else None
            if not config_obj:
                logger.warning(f"No enabled Shopify integration found for tenant {tenant_code}")
                return {"status": "skipped", "reason": "no_integration"}
            instance_id = config_obj.instance_id
        else:
            link = ShopifyShopLink.objects.filter(
                shop_domain=shop_domain,
                status=ShopifyShopLinkStatus.LINKED,
            ).select_related("tenant").first()
            if not link:
                logger.warning(f"No linked tenant for Shopify shop {shop_domain}")
                return {"status": "skipped", "reason": "no_link"}
            tenant = link.tenant
            instance_id = shop_domain.replace(".myshopify.com", "").strip()

        config = get_shopify_config_for_sync(tenant.id, instance_id)
        if not config:
            logger.warning(f"Shopify config not available for tenant {tenant.id} instance {instance_id}")
            return {"status": "skipped", "reason": "no_integration"}

        schema_name = getattr(tenant, "schema_name", None)
        with tenant_schema_context(schema_name):
            sync_service = ShopifySyncService(tenant, config)
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


@shared_task(
    bind=True,
    name="central_hub.integrations.shopify.tasks.periodic_shopify_sync",
    queue=settings.LOW_PRIORITY_Q,
)
def periodic_shopify_sync(self):
    """
    Safety-net periodic full sync for all enabled Shopify integrations.

    Iterates every enabled Shopify IntegrationConfig, checks which resource
    toggles are on, and queues the corresponding sync tasks.
    Schedule via django-celery-beat (e.g. every 4 hours).
    """
    from central_hub.integrations.models import IntegrationConfig

    configs = IntegrationConfig.objects.filter(
        slug="shopify",
        enabled=True,
    ).select_related("tenant")

    queued = 0
    for cfg in configs:
        tenant_id = cfg.tenant_id
        instance_id = cfg.instance_id or "default"
        c = cfg.config or {}

        if c.get("direction") != "receive":
            continue

        if c.get("receive_products"):
            sync_shopify_products.delay(tenant_id=tenant_id, instance_id=instance_id)
            queued += 1
        if c.get("receive_customers"):
            sync_shopify_customers.delay(tenant_id=tenant_id, instance_id=instance_id)
            queued += 1
        if c.get("receive_orders"):
            sync_shopify_orders.delay(tenant_id=tenant_id, instance_id=instance_id)
            queued += 1

    logger.info("periodic_shopify_sync: queued %d sync tasks for %d enabled configs", queued, configs.count())
    return {"status": "ok", "queued": queued}