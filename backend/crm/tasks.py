
import json
import logging
import os
from datetime import datetime, timedelta
from django.conf import settings

from celery import shared_task
from celery._state import current_task
from django.utils import timezone

from crm.core.integrators import register_or_update_ecommerce_order, import_dac_delivery_status, \
    register_shipping_request, send_order_to_dac_fulfillment, send_woocommerce_order_to_zeta, get_customer_code, \
    send_tracking_code_to_user, import_woo_product

from crm.lib.woocommerce_api import WooCommerceAPI
from crm.models import Shipment, EcommerceOrder, Branch, WebhookConfig, KnowledgeItem, WebhookPayload
from crm.lib.moiotools import create_dac_delivery
from moio_platform.lib.google_maps_api import get_geocode

from moio_platform.lib.openai_gpt_api import get_json_response
from central_hub.models import Tenant
from central_hub.tenant_config import get_tenant_config, get_tenant_config_by_id, iter_configs_with_integration_enabled

from central_hub.webhooks.utils import get_handler
logger = logging.getLogger(__name__)


@shared_task(bind=True , queue=settings.LOW_PRIORITY_Q)
def heartbeat(self):

    task_id = current_task.request.id
    q_name = self.request.delivery_info['routing_key']

    logger.info(f'Processing task ---> {task_id} from {q_name}')
    print("❤")


@shared_task(bind=True, queue=settings.LOW_PRIORITY_Q)
def check_dac_deliveries(self):

    task_id = current_task.request.id
    q_name = self.request.delivery_info['routing_key']
    logger.info(f'Processing task ---> {task_id} from {q_name}')

    import_dac_delivery_status()


@shared_task(bind=True, queue=settings.MEDIUM_PRIORITY_Q)
def woocommerce_webhook_processor(self, headers: json, body: json, tenant_code):
    task_id = current_task.request.id
    q_name = self.request.delivery_info['routing_key']
    logger.info(f'Processing woocommerce webhook ---> {task_id} from {q_name}')

    tenant = Tenant.objects.get(tenant_code=tenant_code)

    headers = json.loads(headers)
    payload = json.loads(body)

    topic = headers["topic"]
    webhook_resource = headers["webhook_resource"]

    if topic == 'order.created':

        register_or_update_ecommerce_order(payload, tenant)

    elif topic == 'order.updated':

        register_or_update_ecommerce_order(payload, tenant)

    elif topic == 'coupon.updated':

        print("coupon updated")
        print(f"webhook resource: {webhook_resource}")

        print("================================================")

    elif topic == 'product.created' or topic == 'product.updated':
        print("product updated or updated")
        import_woo_product(payload, tenant)

    else:

        print(f"webhook resource: {webhook_resource}")
        print("Topic:", topic)

        print("================================================")

    print(f"Job {task_id} procesado. ")


@shared_task(bind=True, queue=settings.LOW_PRIORITY_Q)
def geocode_branches(self):
    task_id = current_task.request.id
    q_name = self.request.delivery_info['routing_key']
    logger.info(f'Geocoding Branches ---> {task_id} from {q_name}')

    from tenancy.models import Tenant
    for tenant in Tenant.objects.all():
        tenant_config = get_tenant_config(tenant)
        if tenant_config.google_integration_enabled:
            for branch in Branch.objects.filter(geocoded__exact=False, tenant=tenant_config.tenant):

                address = ""
                if branch.address:
                    address += branch.address
                if branch.city:
                    address += ", " + branch.city
                if branch.state:
                    address += " ," + branch.state
                if branch.postal_code:
                    address += ", " + branch.postal_code

                address = address.strip()
                print(address)

                if address:
                    geocode_result = get_geocode(address=address, google_maps_api_key=tenant_config.google_api_key)
                    print(geocode_result)

                    if geocode_result:
                        branch.latitude = geocode_result[0]["lat"]
                        branch.longitude = geocode_result[0]["lng"]
                        branch.geocoded = True
                        branch.save()
        else:
            print(f"Google Integrations Disabled for {tenant}")


@shared_task(bind=True, queue=settings.MEDIUM_PRIORITY_Q)
def smart_address_fix(self, data, order_number, tenant_id):
    task_id = current_task.request.id
    q_name = self.request.delivery_info['routing_key']
    logger.info(f'Fixig address ---> {task_id} from {q_name}')

    tenant_configuration = get_tenant_config_by_id(tenant_id)
    if tenant_configuration.openai_integration_enabled:
        instructions = "format this address to be compatible and attempt to standardize it. and return it in a json format. We need just the shipping address, if there is none, assume the billing address. The notes field can contain important data to decide what to do. This is an uruguayan address:"
        prompt = f'{instructions} {data}'
        get_json_response(prompt, tenant_configuration.openai_api_key)


@shared_task(bind=True, queue=settings.MEDIUM_PRIORITY_Q)
def fix_order_addresses(self):
    task_id = current_task.request.id
    q_name = self.request.delivery_info['routing_key']
    logger.info(f'Processing task ---> {task_id} from {q_name}')

    from tenancy.models import Tenant
    for tenant in Tenant.objects.all():
        tenant_config = get_tenant_config(tenant)
        if tenant_config.openai_integration_enabled:
            try:
                # Instruction model removed - use default prompt
                instructions = "Clean and normalize this delivery address:"

                for order in EcommerceOrder.objects.filter(tenant=tenant_config.tenant, order_clean_delivery_address__exact=""):

                    prompt = f'{instructions} {order.order_customer_registered_address}'
                    clean_address = get_json_response(prompt, tenant_config.openai_api_key, model="gpt-4-0125-preview")
                    order.order_clean_delivery_address = clean_address
                    order.save()
            except Exception as e:
                print(e)


@shared_task(bind=True, queue=settings.LOW_PRIORITY_Q)
def fetch_frontend_skus_data(self, tenant=None):

    task_id = current_task.request.id
    q_name = self.request.delivery_info['routing_key']
    logger.info(f'Importing skus ---> {task_id} from {q_name}')

    print(f'Tenant: {tenant}')

    if not tenant:
        for _t, tenant_configuration in iter_configs_with_integration_enabled("woocommerce"):
            if tenant_configuration.woocommerce_integration_enabled:
                woo_conn = WooCommerceAPI(
                    consumer_key=tenant_configuration.woocommerce_consumer_key,
                    consumer_secret=tenant_configuration.woocommerce_consumer_secret,
                    url=tenant_configuration.woocommerce_site_url
                )

                products = woo_conn.get_products()
                for product in products:
                    print(f"Importing {product['sku']}, {product['name']}")
                    import_woo_product(product, tenant_configuration.tenant)


@shared_task(bind=True, queue=settings.LOW_PRIORITY_Q)
def import_frontend_skus(self, tenant_id):
    if current_task:
        task_id = current_task.request.id
        q_name = self.request.delivery_info['routing_key']
        logger.info(f'Importing SKUs ---> {task_id} from {q_name}')

    try:
        tenant_configuration = get_tenant_config_by_id(tenant_id)

        if tenant_configuration.woocommerce_integration_enabled:
            woo_conn = WooCommerceAPI(
                consumer_key=tenant_configuration.woocommerce_consumer_key,
                consumer_secret=tenant_configuration.woocommerce_consumer_secret,
                url=tenant_configuration.woocommerce_site_url
            )

            products = woo_conn.get_products()
            for product in products:
                print(f"Importing {product['sku']}, {product['name']}, {product['status']}")
                import_woo_product(product, tenant_configuration.tenant)

    except Tenant.DoesNotExist:
        raise ValueError(f"No existe el tenant {tenant_id}") from None


@shared_task(bind=True, queue=settings.MEDIUM_PRIORITY_Q)
def create_smart_order(self, data, tenant):
    task_id = current_task.request.id
    q_name = self.request.delivery_info['routing_key']
    logger.info(f'Creating order ---> {task_id} from {q_name}')

    tenant_configuration = get_tenant_config_by_id(tenant) if isinstance(tenant, int) else get_tenant_config(tenant)

    system_instructions = """
                            tengo un ecommerce y quiero procesar pedidos de mayoristas que los envian de multiples formas. 
                            Mis SKU tienen un codigo con el siguiente formato por lo general comienzan con una letra, luego tienen 4 o 5 digitos, 
                            luego un guion y luego 3 letras para el codigo de color (a veces son dos letras separadas por - o / ) y tres digitos 
                            para el talle que pueden ser 085, 090, 095, 100, 105, 001, 002, 003, 004. a veces los pedidos tienen errores de formato, quiero corregirlos. 
                            Si no aparecen cantidades, se asume 1 unidad.
                            Estos son los SKU validos:
                            A0032-BLA085
                            A0032-BLA090
                            A0032-BLA095
                            A0032-BLA100
                            A0032-GRI085
                            A0032-GRI090
                            A0032-GRI095
                            A0032-GRI100
                            A0032-NEG085
                            A0032-NEG095
                            A0032-NEG100
                            A0032-NUD090
                            A0032-NUD095
                            A0032-NUD100
                            A0032-SOF090
                            A0032-SOF095
                            A0041-BLA085
                            A0041-BLA090
                            A0041-BLA095
                            A0041-BLA100
                            A0041-HUE085
                            A0041-HUE090
                            A0041-HUE095
                            A0041-HUE100
                            A0041-NEG085
                            A0041-NEG090
                            A0041-NEG095
                            A0041-NEG100
                            A0041-NUD085
                            A0041-NUD090
                            A0041-NUD095
                            A0041-NUD100
                            A0041-SOF085
                            A0041-SOF090
                            A0041-SOF095
                            A0041-SOF100
                            A0042-BLA085
                            A0042-BLA090
                            A0042-BLA095
                            A0042-BLA100
                            A0042-NEG085
                            A0042-NEG090
                            A0042-NEG095
                            A0042-NEG100
                            A0042-NUD085
                            A0042-NUD090
                            A0042-NUD095
                            A0042-NUD100
                            A0042-SOF085
                            A0042-SOF090
                            A0042-SOF095
                            A0042-SOF100
                            A0046-BLA090
                            A0046-BLA095
                            A0046-BLA100
                            A0046-BLA105
                            A0046-NEG090
                            A0046-NEG095
                            A0046-NEG100
                            A0046-NEG105
                            A0046-NUD090
                            A0046-NUD095
                            A0046-NUD100
                            A0046-NUD105
                            A0046-SOF090
                            A0046-SOF095
                            A0046-SOF100
                            A0046-SOF105
                            A0048-NUD090
                            A0048-NUD100
                            A0048-SOF090
                            A0048-SOF095
                            A0048-SOF100
                            A0054-BLA090
                            A0054-BLA095
                            A0054-BLA100
                            A0054-BLA105
                            A0054-NEG090
                            A0054-NEG095
                            A0054-NEG100
                            A0054-NEG105
                            A0054-NUD090
                            A0054-NUD095
                            A0054-NUD100
                            A0054-NUD105
                            A0054-SOF090
                            A0054-SOF095
                            A0054-SOF100
                            A0054-SOF105
                            A0061-BLA095
                            A0061-BLA100
                            A0061-NEG090
                            A0061-NEG095
                            A0061-NEG100
                            A0066-BLA085
                            A0066-BLA090
                            A0066-BLA095
                            A0066-NEG085
                            A0066-NEG090
                            A0066-NEG095
                            A0066-SOF085
                            A0071-NEG085
                            A0071-NEG090
                            A0071-NEG095
                            A0071-NEG100
                            A0072-NEG085
                            A0072-NEG090
                            A0072-NEG095
                            A0072-SOF085
                            A0072-SOF090
                            A0072-SOF095
                            A0072-SOF100
                            A0108-BLA085
                            A0108-BLA090
                            A0108-BLA095
                            A0108-BLA100
                            A0108-NEG085
                            A0108-NEG095
                            A0110-BLA085
                            A0110-BLA090
                            A0110-BLA095
                            A0110-BLA100
                            A0110-GRI090
                            A0110-GRI095
                            A0110-GRI100
                            A0110-NEG085
                            A0110-NEG090
                            A0110-NEG095
                            A0110-NEG100
                            A0111-BLA085
                            A0111-BLA090
                            A0111-BLA095
                            A0111-BLA100
                            A0111-NEG085
                            A0111-NEG090
                            A0111-NEG095
                            A0111-NEG100
                            A0111-TOP090
                            A0111-TOP095
                            A0172-NEG085
                            A0172-NEG090
                            A0172-NEG095
                            A0172-NEG100
                            A1216-AZU085
                            A1216-AZU090
                            A1216-AZU095
                            A1216-AZU100
                            A1216-BLA085
                            A1216-BLA090
                            A1216-BLA095
                            A1216-BLA100
                            A1216-N/R090
                            A1216-N/R095
                            A1216-V/N085
                            A1216-V/N090
                            A1216-V/N095
                            A1216-V/N100
                            A1224-BLA085
                            A1224-BLA090
                            A1224-BLA095
                            A1224-BLA100
                            A1224-NEG085
                            A1224-NEG090
                            A1224-NEG095
                            A1224-NEG100
                            A1224-SOF085
                            A1224-SOF090
                            A1224-SOF095
                            A1224-SOF100
                            A1242-BLA085
                            A1242-BLA090
                            A1242-BLA095
                            A1242-BLA100
                            A1242-NEG085
                            A1242-NEG090
                            A1242-NEG095
                            A1242-NEG100
                            A1242-SOF085
                            A1242-SOF090
                            A1242-SOF095
                            A1242-SOF100
                            A1243-BLA085
                            A1243-BLA090
                            A1243-BLA095
                            A1243-BLA100
                            A1243-NEG085
                            A1243-NEG090
                            A1243-NEG095
                            A1243-NEG100
                            A1243-SOF090
                            A1243-SOF095
                            A1243-SOF100
                            A1243-VIN085
                            A1243-VIN090
                            A1243-VIN095
                            A1243-VIN100
                            A1253-BLA085
                            A1253-BLA090
                            A1253-BLA095
                            A1253-BLA100
                            A1253-GRI085
                            A1253-GRI095
                            A1253-NEG085
                            A1253-NEG090
                            A1253-NEG095
                            E2005-BLA085
                            E2005-BLA090
                            E2005-BLA095
                            E2005-BLA100
                            E2005-NEG085
                            E2005-NEG090
                            E2005-NEG100
                            E2005-NUD085
                            E2005-NUD090
                            E2005-NUD095
                            E2005-NUD100
                            E2006-BLA085
                            E2006-BLA090
                            E2006-BLA095
                            E2006-BLA100
                            E2006-NEG085
                            E2006-NEG090
                            E2006-NEG095
                            E2006-NEG100
                            E2006-NUD085
                            E2006-NUD090
                            E2006-NUD095
                            E2006-NUD100
                            E2007-BLA085
                            E2007-BLA090
                            E2007-BLA095
                            E2007-BLA100
                            E2007-MOS085
                            E2007-MOS090
                            E2007-MOS095
                            E2007-MOS100
                            E2007-NEG085
                            E2007-NEG090
                            E2007-NEG095
                            E2007-RUB085
                            E2007-RUB090
                            E2007-RUB095
                            E2007-RUB100
                            E2007-VEG085
                            E2007-VEG090
                            E2007-VEG095
                            E2007-VEG100
                            E2009-BLA085
                            E2009-BLA090
                            E2009-BLA095
                            E2009-BLA100
                            E2009-NEG085
                            E2009-NEG090
                            E2009-NEG095
                            E2009-NEG100
                            E2009-RUB085
                            E2009-RUB090
                            E2009-RUB095
                            E2009-RUB100
                            E2009-SOF085
                            E2009-SOF090
                            E2009-SOF095
                            E2009-SOF100
                            E2010-NEG085
                            E2010-NEG090
                            E2010-NEG095
                            E2010-NEG100
                            E2010-SOF085
                            E2010-SOF090
                            E2010-SOF095
                            E2010-SOF100
                            E2010-TER085
                            E2010-TER090
                            E2010-TER095
                            E2010-TER100
                            E2012-BLA085
                            E2012-BLA090
                            E2012-BLA095
                            E2012-BLA100
                            E2012-NEG085
                            E2012-NEG090
                            E2012-NEG095
                            E2012-NEG100
                            E2012-SOF085
                            E2012-SOF090
                            E2012-SOF095
                            E2012-SOF100
                            E2012-TER090
                            E2012-TER095
                            E2012-TER100
                            E2021-BLA090
                            E2021-BLA095
                            E2021-BLA100
                            E2021-NEG085
                            E2021-NEG090
                            E2021-NEG095
                            E2021-NEG100
                            E2021-NUD085
                            E2021-NUD090
                            E2021-NUD095
                            E2021-NUD100
                            E2021-ROJ085
                            E2021-ROJ090
                            E2021-ROJ095
                            E2024-BLA090
                            E2024-BLA095
                            E2024-NEG085
                            E2024-NEG090
                            E2024-NEG095
                            E2024-NEG100
                            E2024-ROS085
                            E2024-ROS090
                            E2024-ROS095
                            E2024-ROS100
                            E2025-AZU085
                            E2025-AZU090
                            E2025-BLA100
                            E2025-NEG085
                            E2025-NEG090
                            E2025-NEG095
                            E2025-ROS085
                            E2025-ROS090
                            E2025-ROS095
                            E2025-ROS100
                            E2029-NEG090
                            E2029-NEG095
                            E2029-NEG100
                            E2031-NEG090
                            E2031-NEG095
                            E2031-NEG100
                            E2031-SOF095
                            E2031-SOF100
                            E2033-NEG085
                            E2033-NEG090
                            E2033-NEG100
                            E2035-AZU085
                            E2035-AZU090
                            E2035-AZU095
                            E2035-AZU100
                            E2035-BLA085
                            E2035-BLA090
                            E2035-BLA095
                            E2035-BLA100
                            E2035-NEG085
                            E2035-NEG090
                            E2035-NEG095
                            E2035-NEG100
                            E2035-SOF090
                            E2035-SOF095
                            E2035-SOF100
                            E2040-BLA090
                            E2041-NEG095
                            E2041-NEG100
                            E2042-BLA090
                            E2042-BLA095
                            E2042-NEG085
                            E2042-NEG090
                            E2042-NEG095
                            E2042-NEG100
                            E2043-SOF090
                            E2043-SOF095
                            E2043-VIN085
                            E2043-VIN090
                            E2043-VIN095
                            E2043-VIN100
                            E2044-SOF085
                            E2044-SOF090
                            E2044-SOF095
                            E2044-SOF100
                            E2044-VIN085
                            E2044-VIN090
                            E2044-VIN095
                            E2045-SOF090
                            E2045-SOF095
                            E2046-NEG090
                            E2046-NEG100
                            E2048-NEG085
                            E2048-NEG090
                            E2048-NEG095
                            E2048-RUB085
                            E2048-RUB090
                            E2048-RUB095
                            E2048-RUB100
                            E2048-SOF085
                            E2048-SOF090
                            E2048-SOF095
                            E2049-BLA085
                            E2049-BLA090
                            E2049-BLA095
                            E2049-BLA100
                            E2049-NEG085
                            E2049-NEG090
                            E2049-SOF085
                            E2049-SOF090
                            E2049-SOF095
                            E2049-SOF100
                            E2050-AZU090
                            E2050-AZU095
                            E2050-AZU100
                            E2050-BLA090
                            E2050-BLA095
                            E2050-NEG085
                            E2050-NEG090
                            E2050-NEG095
                            E2050-RUB090
                            E2050-RUB095
                            E2050-SOF085
                            E2050-SOF090
                            E2050-SOF095
                            E2050-SOF100
                            E2055-NEG085
                            E2055-NEG090
                            E2055-NEG095
                            E2055-NEG100
                            E2055-NUD085
                            E2055-NUD090
                            E2055-NUD095
                            E2055-NUD100
                            E2056-NEG001
                            E2056-NEG002
                            E2056-NUD001
                            E2056-NUD002
                            E2057-NEG085
                            E2057-NEG090
                            E2057-NEG095
                            E2057-NEG100
                            E2057-NUD085
                            E2057-NUD090
                            E2057-NUD095
                            E2057-NUD100
                            E2058-BLA085
                            E2058-BLA090
                            E2058-BLA095
                            E2058-BLA100
                            E2058-BLA105
                            E2058-NEG085
                            E2058-NEG090
                            E2058-NEG095
                            E2058-NEG100
                            E2058-NEG105
                            E2059-BLA085
                            E2059-BLA090
                            E2059-BLA095
                            E2059-BLA100
                            E2059-BLA105
                            E2059-NEG085
                            E2059-NEG090
                            E2059-NEG095
                            E2059-NEG100
                            E2059-NEG105
                            E2059-SOF085
                            E2059-SOF090
                            E2059-SOF095
                            E2059-SOF100
                            E2059-SOF105
                            E2110-B/S085
                            E2110-B/S090
                            E2110-B/S095
                            E2110-B/S100
                            E2110-N/S085
                            E2110-N/S090
                            E2110-N/S095
                            E2110-N/S100
                            E2110-N/T085
                            E2110-N/T090
                            E2110-N/T095
                            E2110-N/T100
                            E2131-BLA090
                            E2131-NEG090
                            E2131-ROJ090
                            E2150-BLA085
                            E2150-BLA090
                            E2150-BLA095
                            E2150-BLA100
                            E2150-NEG085
                            E2150-NEG090
                            E2150-NEG095
                            E2150-NEG100
                            E2150-SOF085
                            E2150-SOF090
                            E2150-SOF095
                            E2150-SOF100
                            E2244-SOF090
                            E2244-SOF100
                            E2246-SOF090
                            L5477-BLA085
                            L5477-BLA090
                            L5477-BLA095
                            L5477-BLA100
                            L5477-NEG085
                            L5477-NEG090
                            L5477-NEG095
                            L5477-NEG100
                            L5477-ROJ090
                            L5477-ROJ095
                            L5477-ROS085
                            L5477-ROS090
                            L5477-ROS095
                            L5477-ROS100
                            L5477-SOF085
                            L5477-SOF090
                            L5477-SOF095
                            L5477-VEG085
                            L5477-VEG090
                            L5477-VEG095
                            L5477-VEG100
                            L5495-BLA085
                            L5495-BLA090
                            L5495-BLA095
                            L5495-NEG085
                            L5495-NEG090
                            L5495-NEG095
                            L5495-NEG100
                            L5495-NUD085
                            L5495-NUD090
                            L5495-NUD095
                            L5495-NUD100
                            L5495-NUD105
                            L5495-RSE085
                            L5495-RSE090
                            L5495-RSE095
                            L5495-RSE100
                            L5495-SOF085
                            L5495-SOF090
                            L5495-SOF095
                            L5495-SOF100
                            L5495-SOF105
                            L5589-AZU085
                            L5589-AZU090
                            L5589-AZU095
                            L5589-AZU100
                            L5589-BLA085
                            L5589-BLA090
                            L5589-BLA095
                            L5589-BLA100
                            L5589-FRU085
                            L5589-FRU090
                            L5589-FRU095
                            L5589-FRU100
                            L5589-FUC085
                            L5589-FUC090
                            L5589-FUC095
                            L5589-FUC100
                            L5589-MAL085
                            L5589-MAL090
                            L5589-MAL095
                            L5589-MAL100
                            L5589-NEG085
                            L5589-NEG090
                            L5589-NEG095
                            L5589-NEG100
                            L5589-ROJ095
                            L5589-SOF085
                            L5589-SOF090
                            L5589-SOF095
                            L5589-VIN090
                            L5589-VIN095
                            L5607-BLA085
                            L5607-BLA090
                            L5607-BLA095
                            L5607-BLA100
                            L5607-NEG085
                            L5607-NEG090
                            L5607-NEG095
                            L5607-NEG100
                            L5607-NUD085
                            L5607-NUD090
                            L5607-NUD095
                            L5607-NUD100
                            L5607-SOF085
                            L5607-SOF090
                            L5607-SOF095
                            L5608-BLA085
                            L5608-BLA090
                            L5608-BLA095
                            L5608-BLA100
                            L5608-CRU085
                            L5608-CRU090
                            L5608-CRU095
                            L5608-CRU100
                            L5608-NEG085
                            L5608-NEG090
                            L5608-NEG095
                            L5608-NEG100
                            L5608-ROJ085
                            L5608-ROJ090
                            L5608-ROJ095
                            L5608-ROJ100
                            L5608-RPE085
                            L5608-RPE090
                            L5608-RPE095
                            L5608-RPE100
                            L5627-AZU085
                            L5627-AZU090
                            L5627-AZU095
                            L5627-AZU100
                            L5627-BLA085
                            L5627-BLA090
                            L5627-BLA095
                            L5627-BLA100
                            L5627-NEG085
                            L5627-NEG090
                            L5627-NEG095
                            L5627-NEG100
                            L5627-SCA085
                            L5627-SCA090
                            L5627-SCA095
                            L5627-SCA100
                            L5651-NEG001
                            L5651-NEG002
                            L5651-NEG003
                            L5651-NEG004
                            L5667-BLA085
                            L5667-BLA090
                            L5667-BLA095
                            L5667-BLA100
                            L5667-NEG085
                            L5667-NEG095
                            L5667-NEG100
                            L5667-RPE085
                            L5667-RPE090
                            L5667-RPE095
                            L5667-RPE100
                            L5668-BLA085
                            L5668-BLA090
                            L5668-BLA095
                            L5668-BLA100
                            L5668-NEG085
                            L5668-NEG090
                            L5668-NEG095
                            L5673-BLA095
                            L5673-BLA100
                            L5687-BLA085
                            L5687-BLA090
                            L5687-BLA095
                            L5687-BLA100
                            L5687-NEG085
                            L5687-NEG090
                            L5687-NEG095
                            L5687-NEG100
                            L5687-NUD085
                            L5687-NUD090
                            L5687-NUD095
                            L5687-NUD100
                            L5687-RSE085
                            L5687-RSE090
                            L5687-RSE095
                            L5687-RSE100
                            L5688-BLA085
                            L5688-BLA090
                            L5688-BLA095
                            L5688-BLA100
                            L5688-BLA105
                            L5688-NEG085
                            L5688-NEG090
                            L5688-NEG095
                            L5688-NEG100
                            L5688-NEG105
                            L5688-RUB085
                            L5688-RUB090
                            L5688-RUB095
                            L5688-RUB100
                            L5688-RUB105
                            L5688-TIB085
                            L5688-TIB090
                            L5688-TIB095
                            L5688-TIB100
                            L5688-TIB105
                            L5689-AZU085
                            L5689-AZU090
                            L5689-AZU095
                            L5689-AZU100
                            L5689-AZU105
                            L5689-BLA085
                            L5689-BLA090
                            L5689-BLA095
                            L5689-BLA100
                            L5689-BLA105
                            L5689-NEG085
                            L5689-NEG090
                            L5689-NEG095
                            L5689-ROS085
                            L5689-ROS090
                            L5689-ROS095
                            L5689-ROS100
                            L5700-NEG085
                            L5700-NEG090
                            L5707-BLA085
                            L5707-BLA090
                            L5722-BLA085
                            L5722-BLA095
                            L5722-NEG095
                            L5723-BLA085
                            L5723-BLA090
                            L5723-BLA095
                            L5723-NEG085
                            L5723-NEG090
                            L5723-NEG095
                            L5723-NEG100
                            L5723-RPE085
                            L5723-RPE090
                            L5723-RPE095
                            L5723-RPE100
                            L5725-BLA085
                            L5725-BLA090
                            L5725-BLA095
                            L5725-BLA100
                            L5725-BLA105
                            L5725-NEG085
                            L5725-NEG090
                            L5725-NEG095
                            L5725-NEG100
                            L5725-NEG105
                            L5726-ENE085
                            L5726-ENE090
                            L5726-ENE095
                            L5726-ENE100
                            L5726-NEG085
                            L5730-BLA085
                            L5730-BLA090
                            L5730-BLA095
                            L5730-BLA100
                            L5730-NEG085
                            L5730-NEG090
                            L5730-NEG095
                            L5730-NEG100
                            L5730-RUB085
                            L5730-RUB090
                            L5730-RUB095
                            L5730-RUB100
                            L5733-ARC085
                            L5733-ARC090
                            L5733-ARC095
                            L5733-BLA085
                            L5733-BLA090
                            L5733-BLA095
                            L5733-BLA100
                            L5733-NEG085
                            L5733-NEG090
                            L5733-NEG095
                            L5733-NEG100
                            L5733-OCE090
                            L5733-OCE095
                            L5735-NEG085
                            L5735-NEG090
                            L5735-NEG095
                            L5735-NEG100
                            L5737-BLA090
                            L5737-NEG090
                            L5737-ROJ090
                            L5738-BLA095
                            L5738-BLA100
                            L5739-BLA090
                            L5739-BLA100
                            L5739-NEG090
                            L5739-NEG100
                            L5739-ROJ090
                            L5739-ROJ100
                            L5744-AZU085
                            L5744-AZU090
                            L5744-AZU095
                            L5744-AZU100
                            L5744-BLA085
                            L5744-BLA090
                            L5744-BLA095
                            L5744-BLA100
                            L5744-NEG085
                            L5744-NEG090
                            L5744-NEG095
                            L5744-NEG100
                            L5744-SCA085
                            L5744-SCA090
                            L5744-SCA095
                            L5744-SCA100
                            L5745-BLA085
                            L5745-BLA090
                            L5745-BLA095
                            L5745-BLA100
                            L5745-NEG085
                            L5745-NEG090
                            L5745-NEG095
                            L5745-NEG100
                            L5747-NEG085
                            L5747-NEG090
                            L5747-NEG095
                            L5747-NEG100
                            L5747-SOF085
                            L5747-SOF090
                            L5747-SOF095
                            L5747-SOF100
                            L5747-TIB085
                            L5747-TIB090
                            L5747-TIB095
                            L5747-TIB100
                            L5748-BLA085
                            L5748-BLA090
                            L5748-NEG085
                            L5748-NEG090
                            L5748-SOF085
                            L5748-SOF090
                            L5748-SOF095
                            L5748-SOF100
                            L5749-BLA085
                            L5749-BLA090
                            L5749-BLA095
                            L5749-BLA100
                            L5749-NEG085
                            L5749-NEG090
                            L5749-NEG095
                            L5749-NEG100
                            L5749-SOF085
                            L5749-SOF090
                            L5749-SOF095
                            L5749-SOF100
                            L5750-NEG085
                            L5750-NEG090
                            L5750-NEG095
                            L5750-NEG100
                            L5751-NEG085
                            L5751-NEG095
                            L5752-NEG085
                            L5752-NEG090
                            L5752-NEG095
                            L5752-NEG100
                            L5753-AZU085
                            L5753-AZU090
                            L5753-AZU095
                            L5753-AZU100
                            L5753-ECA085
                            L5753-ECA090
                            L5753-ECA095
                            L5753-ECA100
                            L5753-ENE085
                            L5753-ENE090
                            L5753-ENE095
                            L5753-ENE100
                            L5753-NEG085
                            L5753-NEG090
                            L5753-NEG095
                            L5753-NEG100
                            L5754-FUC085
                            L5754-FUC090
                            L5754-FUC095
                            L5754-FUC100
                            L5754-NEG085
                            L5754-NEG090
                            L5754-NEG095
                            L5754-NEG100
                            L5756-NEG085
                            L5756-NEG090
                            L5756-NEG095
                            L5756-NEG100
                            L5756-NEG105
                            L5756-RUB090
                            L5756-RUB095
                            L5756-RUB100
                            L5756-RUB105
                            L5757-NEG085
                            L5757-NEG090
                            L5757-NEG095
                            L5757-NEG100
                            L5758-N/N085
                            L5758-N/N090
                            L5758-N/N095
                            L5758-N/N100
                            L5758-NEG085
                            L5758-NEG090
                            L5758-NEG095
                            L5759-AZU001
                            L5759-AZU003
                            L5759-AZU004
                            L5759-ECA001
                            L5759-ECA002
                            L5759-ECA003
                            L5759-ECA004
                            L5759-NEG001
                            L5759-NEG002
                            L5759-NEG003
                            L5759-NEG004
                            L5760-NEG085
                            L5760-NEG090
                            L5760-NEG095
                            L5760-NEG100
                            L5761-FUC085
                            L5761-FUC090
                            L5761-FUC095
                            L5761-FUC100
                            M23051-NAR001
                            M23051-NAR002
                            M23051-NAR003
                            M23051-NAR004
                            M23051-TUR001
                            M23051-TUR002
                            M23051-TUR004
                            M23052-NAR002
                            M23052-NAR003
                            M23052-TUR001
                            M23052-TUR002
                            M23052-TUR003
                            M23052-TUR004
                            M23052-TUR005
                            M23053-FUC001
                            M23053-FUC002
                            M23053-FUC003
                            M23053-FUC004
                            M23053-GRI001
                            M23053-GRI002
                            M23053-GRI003
                            M23053-GRI004
                            M23053-GRI005
                            M23054-AZU001
                            M23054-AZU002
                            M23054-AZU003
                            M23054-BRO001
                            M23054-BRO002
                            M23054-BRO003
                            M23054-NEG001
                            M23054-NEG002
                            M23054-NEG003
                            M23055-AZU001
                            M23055-AZU002
                            M23055-AZU003
                            M23055-BRO001
                            M23055-BRO002
                            M23055-BRO003
                            M23055-BRO004
                            M23055-NEG001
                            M23055-NEG002
                            M23055-NEG003
                            M23056-LIM001
                            M23056-LIM002
                            M23056-LIM003
                            M23056-LIM004
                            M23056-NEG001
                            M23056-NEG002
                            M23056-NEG003
                            M23056-NEG004
                            M23056-RUB001
                            M23056-RUB002
                            M23056-RUB003
                            M23061-BLA002
                            M23061-BLA003
                            M23061-LIL001
                            M23061-LIL002
                            M23061-LIL003
                            M23061-LIL004
                            M23061-NAR001
                            M23061-NAR002
                            M23061-NAR003
                            M23061-NAR004
                            M23061-NEG001
                            M23061-NEG002
                            M23061-NEG003
                            M23061-NEG004
                            M23061-VER002
                            M23061-VER003
                            M23064-CHO001
                            M23064-CHO002
                            M23064-CHO003
                            M23064-CHO004
                            M23064-FUC001
                            M23064-FUC002
                            M23064-FUC003
                            M23064-FUC004
                            M23064-NAR001
                            M23064-NAR002
                            M23064-NAR003
                            M23064-NAR004
                            M23064-NEG001
                            M23064-NEG002
                            M23064-NEG003
                            M23064-NEG004
                            M23065-LIL001
                            M23065-LIL002
                            M23065-LIL003
                            M23065-LIL004
                            M23065-NEG001
                            M23065-NEG002
                            M23065-NEG004
                            M23066-BLA002
                            M23066-BLA003
                            M23066-NAR002
                            M23066-NAR003
                            M23066-NAR004
                            M23066-NEG002
                            M23067-BLA001
                            M23067-BLA002
                            M23067-BLA003
                            M23067-NEG002
                            M23067-NEG003
                            M23067-VIO001
                            M23067-VIO002
                            M23067-VIO003
                            M23067-VIO004
                            M23068-CHO001
                            M23068-CHO002
                            M23068-CHO003
                            M23068-CHO004
                            M23068-FUC001
                            M23068-FUC002
                            M23068-FUC003
                            M23068-FUC004
                            M23068-NEG001
                            M23068-NEG002
                            M23068-NEG003
                            M23069-FUC002
                            M23069-FUC003
                            M23069-NAR001
                            M23069-NAR002
                            M23069-NAR003
                            M23069-NAR004
                            M23069-NEG002
                            M23069-NEG003
                            M23070-NEG001
                            M23070-NEG002
                            M23070-NEG003
                            M23070-PET001
                            M23070-PET002
                            M23070-PET003
                            M23070-PET004
                            M23070-TOS001
                            M23070-TOS002
                            M23070-TOS003
                            M23070-TOS004
                            M23071-NEG001
                            M23071-NEG002
                            M23071-NEG003
                            M23071-NEG004
                            M23072-NAR002
                            M23072-NAR004
                            M23072-NEG002
                            M23072-TUR002
                            M23072-TUR004
                            M23073-NEG002
                            M23073-NEG004
                            M23074-NEG002
                            M23074-NEG003
                            M23075-NEG001
                            M23075-NEG002
                            M23075-NEG003
                            M23075-NEG004
                            M23076-BLA003
                            M23076-LIL002
                            M23076-NEG001
                            M23076-NEG002
                            M23076-NEG003
                            M23077-BLA003
                            M23077-LIL003
                            M23077-NEG003
                            M23078-NEG003
                            M23078-NEG004
                            M23079-FUC001
                            M23079-FUC002
                            M23079-FUC003
                            M23079-FUC004
                            M23079-GRI001
                            M23079-GRI002
                            M23079-GRI003
                            M23079-GRI004
                            M23079-NEG001
                            M23079-NEG002
                            M23079-NEG003
                            M23079-NEG004
                            P005-UNI001
                            P005-UNI002
                            P005-UNI003
                            P033-SU1001
                            P033-SU1002
                            P033-SU1003
                            P033-SU1004
                            P033-SU2001
                            P033-SU2002
                            P033-SU2003
                            P033-SU2004
                            P034-SU1002
                            P034-SU1003
                            P034-SU2001
                            P034-SU2002
                            P034-SU2003
                            P034-SU2004
                            P035-SU1001
                            P035-SU1002
                            P035-SU1003
                            P035-SU1004
                            P035-SU2001
                            P035-SU2002
                            P035-SU2003
                            P035-SU2004
                            P060-B/N001
                            P060-B/N002
                            P060-N/S001
                            P060-N/S002
                            P060-N/S003
                            P061-APR001
                            P061-APR002
                            P061-APR003
                            P064-B/S001
                            P064-B/S002
                            P064-B/S003
                            P064-N/N001
                            P064-N/N002
                            P064-N/N003
                            P068-B/N001
                            P068-B/N002
                            P068-B/N003
                            P068-G/M001
                            P068-G/M002
                            P068-G/M003
                            P068-N/G001
                            P068-N/G002
                            P068-N/G003
                            P069-B/N001
                            P069-B/N002
                            P069-B/N003
                            P069-N/G001
                            P069-N/G002
                            P069-N/G003
                            P070-B/S001
                            P070-B/S002
                            P070-B/S003
                            P070-N/S001
                            P070-N/S003
                            P071-B/S001
                            P071-B/S002
                            P071-B/S003
                            P071-N/N001
                            P071-N/N002
                            P071-N/N003
                            P071-N/R001
                            P071-N/R002
                            P072-B/S001
                            P072-B/S002
                            P072-B/S003
                            P072-N/N001
                            P072-N/N002
                            P072-N/N003
                            P072-N/R001
                            P072-N/R002
                            P072-N/R003
                            P074-B/S001
                            P074-B/S003
                            P074-N/R001
                            P074-N/R002
                            P074-N/R003
                            P077-SUR001
                            P077-SUR002
                            P077-SUR003
                            P078-B/S001
                            P078-B/S002
                            P078-B/S003
                            P078-N/N001
                            P078-N/N002
                            P078-N/N003
                            P079-B/A001
                            P079-B/A002
                            P079-B/A003
                            P079-B/A004
                            P079-N/N001
                            P079-N/N002
                            P079-N/N003
                            P079-N/N004
                            P081-B/S001
                            P081-B/S002
                            P081-B/S003
                            P081-B/S004
                            P081-N/N001
                            P081-N/N002
                            P081-N/N003
                            P081-N/N004
                            P083-B/S001
                            P083-B/S002
                            P083-B/S003
                            P083-N/N001
                            P083-N/N002
                            P083-N/N003
                            P086-COR001
                            P086-COR002
                            P086-COR003
                            P086-PET001
                            P086-PET002
                            P086-PET003
                            P088-NEG001
                            P088-NEG002
                            P088-NEG003
                            P089-NEG001
                            P089-NEG002
                            P089-NEG003
                            P089-ROJ001
                            P089-ROJ002
                            P089-ROJ003
                            P100-B/N001
                            P100-B/N002
                            P100-B/N003
                            P100-B/N004
                            P100-N/N001
                            P100-N/N002
                            P100-N/N003
                            P100-N/N004
                            """

    data = f"Responder un JSON con la siguiente estructura: customer:dejar vacio si no se conoce,customer_code: dejar vacio si no se conoce, items:[sku, quantity] a estos datos: {data}"

    order_details = get_json_response(data=data, system_instructions=system_instructions, openai_api_key=tenant_configuration.openai_api_key)
    order_details = json.loads(order_details)

    return order_details


@shared_task(bind=True, queue=settings.MEDIUM_PRIORITY_Q)
def process_received_order(self, order_number):
    task_id = current_task.request.id
    q_name = self.request.delivery_info['routing_key']
    logger.info(f'GProcessing order ---> {task_id} from {q_name}')

    order = EcommerceOrder.objects.get(order_number=order_number)

    print(f'Processing: {order.order_number}')
    shipping_request = register_shipping_request(order)

    tracking_code = create_dac_delivery(shipping_request)
    print(f'Tracking code: {tracking_code}')

    result = send_order_to_dac_fulfillment(order, tracking_code=tracking_code)
    print(f'Notify fulfillment: {result}')

    customer_code = get_customer_code(order)

    print(f'Creating Invoice')
    send_woocommerce_order_to_zeta(order, customer_code)

    print("Informing Tracking Code to Customer")
    if tracking_code:
        send_tracking_code_to_user(order, tracking_code)

        order.tracking_code = tracking_code
        order.save()


@shared_task(bind=True, queue=settings.MEDIUM_PRIORITY_Q, max_retries=3, soft_time_limit=120)
def generic_webhook_handler(self, payload, headers, content_type, webhook_id):
    """
    Celery entry-point for **all** incoming webhooks.
    Resolves the configured handler and delegates the work.
    Also triggers any linked flows.
    """
    task_id = self.request.id
    queue = self.request.delivery_info.get("routing_key")
    logger.debug("Generic webhook %s from %s", task_id, queue)

    try:
        cfg = WebhookConfig.objects.select_related("tenant").get(id=webhook_id)

    except WebhookConfig.DoesNotExist:
        logger.error("WebhookConfig %s missing – dropping payload", webhook_id)
        return "No Handler Configured"

    try:
        if cfg.store_payloads:
            WebhookPayload.objects.create(tenanat=cfg.tenant, config=cfg, payload=payload, status="received")

    except Exception as e:
        logger.error(str(e))

    # Resolve callable: registry key OR dotted path
    handler_result = None
    try:
        if cfg.handler_path:
            handler = get_handler(cfg.handler_path)
        else:
            handler = get_handler("default_handler")

    except Exception as exc:   # dotted import can throw many things
        logger.exception("Unable to resolve handler '%s'", cfg.handler_path)
        # Surface as a hard failure so Celery retry logic kicks in (up to max_retries)
        raise self.retry(exc=exc, countdown=60)

    # Call the worker
    try:
        logger.info("Webhook %s handled by %s", webhook_id, cfg.handler_path)
        handler_result = handler(payload, headers, content_type, cfg)

    except Exception as exc:
        logger.exception("Handler '%s' crashed", cfg.handler_path)
        raise self.retry(exc=exc, countdown=120)

    return handler_result


# =============================================================================
# Anchored Activity Capture (capture → classify → review → apply)
# =============================================================================


@shared_task(bind=True, queue=settings.MEDIUM_PRIORITY_Q, max_retries=3, soft_time_limit=120)
def classify_capture_entry(self, entry_id: str):
    from django.db import transaction
    from crm.models import ActivityCaptureEntry, CaptureEntryAuditEvent, CaptureStatus
    from crm.services.activity_capture_service import (
        AUTO_APPLY_MIN_CONFIDENCE,
        classify_entry_via_openai,
    )

    try:
        entry = ActivityCaptureEntry.objects.select_related("tenant", "actor").get(id=entry_id)
    except ActivityCaptureEntry.DoesNotExist:
        return {"ok": False, "error": "not_found"}

    # Fast exit: already classified/applied
    if entry.status in {CaptureStatus.APPLIED, CaptureStatus.APPLYING}:
        return {"ok": True, "skipped": True, "status": entry.status}

    # Mark as classifying (short transaction)
    with transaction.atomic():
        locked = (
            ActivityCaptureEntry.objects.select_for_update()
            .select_related("tenant", "actor")
            .get(id=entry.id)
        )
        if locked.status not in {CaptureStatus.CAPTURED, CaptureStatus.FAILED}:
            return {"ok": True, "skipped": True, "status": locked.status}
        locked.status = CaptureStatus.CLASSIFYING
        locked.error_details = None
        locked.save(update_fields=["status", "error_details", "updated_at"])
        CaptureEntryAuditEvent.objects.create(
            tenant=locked.tenant,
            entry=locked,
            actor=locked.actor,
            event_type="classify_started",
            event_data={},
        )

    try:
        output = classify_entry_via_openai(entry=entry)
    except Exception as exc:
        logger.exception("classify_capture_entry failed")
        err_str = str(exc)
        unsupported_note = "Configured Model does not support structured Outputs"
        with transaction.atomic():
            locked = ActivityCaptureEntry.objects.select_for_update().get(id=entry.id)
            locked.status = CaptureStatus.FAILED
            locked.error_details = (
                {"error": err_str, "note": unsupported_note}
                if unsupported_note in err_str
                else {"error": err_str}
            )
            locked.save(update_fields=["status", "error_details", "updated_at"])
            CaptureEntryAuditEvent.objects.create(
                tenant=locked.tenant,
                entry=locked,
                actor=locked.actor,
                event_type="classify_failed",
                event_data=locked.error_details,
            )
        raise self.retry(exc=exc, countdown=120)

    payload = output.model_dump()
    suggested = payload.get("suggested_activities")
    suggested_list = suggested if isinstance(suggested, list) else []

    needs_review = bool(payload.get("needs_review")) or float(payload.get("confidence") or 0.0) < AUTO_APPLY_MIN_CONFIDENCE
    new_status = CaptureStatus.NEEDS_REVIEW if needs_review else CaptureStatus.CLASSIFIED

    with transaction.atomic():
        locked = ActivityCaptureEntry.objects.select_for_update().get(id=entry.id)
        locked.raw_llm_response = payload
        locked.classification = payload
        locked.suggested_activities = suggested_list
        locked.summary = payload.get("summary")
        locked.confidence = payload.get("confidence")
        locked.needs_review = needs_review
        locked.review_reasons = payload.get("review_reasons") or []
        locked.status = new_status
        locked.save(
            update_fields=[
                "raw_llm_response",
                "classification",
                "suggested_activities",
                "summary",
                "confidence",
                "needs_review",
                "review_reasons",
                "status",
                "updated_at",
            ]
        )
        CaptureEntryAuditEvent.objects.create(
            tenant=locked.tenant,
            entry=locked,
            actor=locked.actor,
            event_type="classified",
            event_data={
                "confidence": locked.confidence,
                "needs_review": locked.needs_review,
                "review_reasons": locked.review_reasons,
            },
        )
        try:
            from moio_platform.core.events import emit_event

            emit_event(
                name="crm.capture_entry.classified",
                tenant_id=locked.tenant_id,
                entity={"type": "capture_entry", "id": str(locked.id)},
                payload={
                    "entry_id": str(locked.id),
                    "anchor_model": locked.anchor_model,
                    "anchor_id": locked.anchor_id,
                    "status": locked.status,
                    "confidence": locked.confidence,
                    "needs_review": locked.needs_review,
                },
                source="task",
            )
        except Exception:
            pass

    if new_status == CaptureStatus.CLASSIFIED:
        # chain apply async
        apply_capture_entry.delay(entry_id)
    return {"ok": True, "status": new_status, "needs_review": needs_review}


@shared_task(bind=True, queue=settings.MEDIUM_PRIORITY_Q, max_retries=3, soft_time_limit=120)
def apply_capture_entry(self, entry_id: str):
    from django.db import transaction
    from crm.models import ActivityCaptureEntry, CaptureEntryAuditEvent, CaptureStatus
    from crm.services.activity_capture_service import apply_capture_entry_to_activities

    try:
        entry = ActivityCaptureEntry.objects.select_related("tenant", "actor").get(id=entry_id)
    except ActivityCaptureEntry.DoesNotExist:
        return {"ok": False, "error": "not_found"}

    if entry.applied_refs:
        return {"ok": True, "skipped": True, "status": entry.status, "applied_refs": entry.applied_refs}

    # Move into APPLYING under lock.
    with transaction.atomic():
        locked = ActivityCaptureEntry.objects.select_for_update().select_related("actor").get(id=entry.id)
        if locked.applied_refs:
            return {"ok": True, "skipped": True, "status": locked.status, "applied_refs": locked.applied_refs}
        if isinstance(locked.final, dict) and locked.final.get("rejected") is True:
            return {"ok": True, "skipped": True, "status": locked.status, "rejected": True}
        if locked.status not in {CaptureStatus.CLASSIFIED, CaptureStatus.REVIEWED}:
            return {"ok": True, "skipped": True, "status": locked.status}
        locked.status = CaptureStatus.APPLYING
        locked.save(update_fields=["status", "updated_at"])
        CaptureEntryAuditEvent.objects.create(
            tenant=locked.tenant,
            entry=locked,
            actor=locked.actor,
            event_type="apply_started",
            event_data={},
        )

    try:
        result = apply_capture_entry_to_activities(entry=entry, actor=entry.actor)
        activity_ids = result.get("activity_record_ids") or []
        deal_ids = result.get("deal_ids") or []
        refs = [
            *[{"model": "crm.activity", "id": aid} for aid in activity_ids],
            *[{"model": "crm.deal", "id": did} for did in deal_ids],
        ]
    except Exception as exc:
        logger.exception("apply_capture_entry failed")
        with transaction.atomic():
            locked = ActivityCaptureEntry.objects.select_for_update().get(id=entry.id)
            # In apply failures, route to review instead of hard failing where possible.
            locked.status = CaptureStatus.NEEDS_REVIEW
            locked.needs_review = True
            reasons = locked.review_reasons or []
            reasons.append(f"apply_failed:{str(exc)}")
            locked.review_reasons = reasons
            locked.error_details = {"error": str(exc)}
            locked.save(update_fields=["status", "needs_review", "review_reasons", "error_details", "updated_at"])
            CaptureEntryAuditEvent.objects.create(
                tenant=locked.tenant,
                entry=locked,
                actor=locked.actor,
                event_type="apply_failed",
                event_data={"error": str(exc)},
            )
        raise

    with transaction.atomic():
        locked = ActivityCaptureEntry.objects.select_for_update().get(id=entry.id)
        locked.applied_refs = refs
        locked.status = CaptureStatus.APPLIED
        locked.save(update_fields=["applied_refs", "status", "updated_at"])
        CaptureEntryAuditEvent.objects.create(
            tenant=locked.tenant,
            entry=locked,
            actor=locked.actor,
            event_type="applied",
            event_data={"applied_refs": refs},
        )
        try:
            from moio_platform.core.events import emit_event

            emit_event(
                name="crm.capture_entry.applied",
                tenant_id=locked.tenant_id,
                entity={"type": "capture_entry", "id": str(locked.id)},
                payload={
                    "entry_id": str(locked.id),
                    "anchor_model": locked.anchor_model,
                    "anchor_id": locked.anchor_id,
                    "status": locked.status,
                    "applied_refs": refs,
                },
                source="task",
            )
        except Exception:
            pass
    return {"ok": True, "status": CaptureStatus.APPLIED, "applied_refs": refs}




