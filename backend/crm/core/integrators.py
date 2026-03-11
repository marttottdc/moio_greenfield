# IMPORT UTILS
import json
import logging
from datetime import datetime, timedelta

from django.conf import settings
from django.core.mail import EmailMessage
from django.utils import timezone

# IMPORT APIS
from crm.lib.dac_api import DacApi
from crm.lib.moiotools import create_order_details_excel, get_shipping_method
from crm.models import Shipment, EcommerceOrder, EcommerceOrderLine, Address, Product, Tag
from crm.lib.woocommerce_api import WooCommerceAPI, get_product_brand, get_product_category, get_product_price, \
    get_product_sale_price, get_product_tags, get_product_main_image
from crm.lib.zetasoftware_api import ZetaSoftwareAPI
from central_hub.tenant_config import get_tenant_config, iter_configs_with_integration_enabled
import logging

# Configure a logger for this module
logger = logging.getLogger(__name__)
# You can configure logging level/format once in your app’s entry point, for example:
# logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(name)s: %(message)s')


def get_customer_code(ecommerce_order: EcommerceOrder):
    """
    Get customer code of existing Customer in ZetaSoftware
    or create the customer in not found. Return the new code
    Provide an Order["billing"] object from Woocommerce
    """

    config = get_tenant_config(ecommerce_order.tenant)

    if not config.zetaSoftware_integration_enabled:
        raise Exception("Zeta software integration disabled")

    zeta_conn = ZetaSoftwareAPI(devCode=config.zetaSoftware_dev_code,
                                devKey=config.zetaSoftware_dev_key,
                                compayCode=config.zetaSoftware_company_code,
                                companyKey=config.zetaSoftware_company_key)

    order = ecommerce_order.payload
    billing = order["billing"]

    zeta_customer_code = zeta_conn.get_customercode(billing["email"])

    if zeta_customer_code is not None:

        print(f"actualizar cliente {zeta_customer_code}")

    else:

        zeta_customer_code = zeta_conn.get_next_code()
        print(f"crear cliente {zeta_customer_code}")

    customer_data = {
        "Codigo": zeta_customer_code,
        "Nombre": billing["first_name"] + " " + billing["last_name"],
        "RazonSocial": billing["first_name"] + " " + billing["last_name"],
        "EsCliente": "S",
        "EsProveedor": "N",
        "ContactoActivo": "S",
        "PaisCodigo": "UY",
        "DepartamentoCodigo": billing["state"][-2:],
        "Localidad": billing["city"],
        "Direccion": billing["address_1"],
        "CodigoPostal": billing["postcode"],
        "Celular": billing["phone"],
        "Email1": billing["email"],
        "Notas": "",
    }

    zeta_conn.create_or_update_customer(customer_data)

    return zeta_customer_code


def send_woocommerce_order_to_zeta(ecommerce_order: EcommerceOrder, customer_code):
    """
    TODO:
    :param ecommerce_order:
    :param customer_code:
    :return:
    """

    order = ecommerce_order.payload
    config = get_tenant_config(ecommerce_order.tenant)

    if not config.zetaSoftware_integration_enabled:
        raise Exception("Zeta software integration disabled")

    if not config.woocommerce_integration_enabled:
        raise Exception("Woocommerce integration disabled")

    woo_conn = WooCommerceAPI(url=config.woocommerce_site_url,
                              consumer_key=config.woocommerce_consumer_key,
                              consumer_secret=config.woocommerce_consumer_secret)

    zeta_conn = ZetaSoftwareAPI(devCode=config.zetaSoftware_dev_code,
                                devKey=config.zetaSoftware_dev_key,
                                compayCode=config.zetaSoftware_company_code,
                                companyKey=config.zetaSoftware_company_key)

    if woo_conn.is_synced(order):
        print("already synced")
        return "already synced"

    else:
        header = {
            "id": order["id"],
            "number": order["number"],
            "woo_key": order["id"],
            "status": order["status"],
            "date_created": order["date_created"],
            "data_modified": order["date_modified"],
            "woo_customer_id": order["customer_id"],
            "payment_method": order["payment_method"],
            "discounts_total": order["discount_total"],
            "shipping_total": str(int(order["shipping_total"]) + int(order["shipping_tax"])),
            "total": order["total"],
            "created_via": order["created_via"],
            "date_completed": order["date_completed"],
            "date_paid": order["date_paid"],
            "customer_ip": order["customer_ip_address"],
            "customer_device": order["customer_user_agent"],
        }

        dest_order_lines = []
        order_items = order["line_items"]
        for item in order_items:

            dest_order_item = {
                "CodigoArticulo": item["sku"],
                "Cantidad": item["quantity"],
                "PrecioUnitario": round(float(item["price"]) * 1.22, 0),
                "Descuento1": 0,
                "Descuento2": 0,
                "Descuento3": 0,
                "CodigoIVA": 2,
                "Notas": ""
            }
            dest_order_lines.append(dest_order_item)

        if int(header["shipping_total"]) > 0:
            dest_order_shipping_cost = {
                "CodigoArticulo": "ENV001",
                "Concepto": "Envio",
                "Cantidad": 1,
                "PrecioUnitario": float(header["shipping_total"]),
                "Descuento1": 0,
                "Descuento2": 0,
                "Descuento3": 0,
                "CodigoIVA": 2,
                "Notas": ""
            }
            dest_order_lines.append(dest_order_shipping_cost)

        # Formatear Fecha
        date_obj = datetime.strptime(header["data_modified"], '%Y-%m-%dT%H:%M:%S')
        order_date = date_obj.strftime('%Y%m%d')

        customer_type = zeta_conn.get_customer_type(customer_code)

        new_order = {
            "Movimiento":
                {
                    "CodigoComprobante": 101,
                    "Fecha": order_date,
                    "CodigoMoneda": 1,
                    "CodigoCliente": customer_code,
                    "CodigoVendedor": "4",
                    "CodigoPrecio": 1,
                    "CodigoDepositoOrigen": 4,
                    "CodigoReferencia": header["number"],
                    "Notas": f'Pedido #: {header["number"]}',
                    "FechaEntrega": order_date,
                    "CodigoLocal": 1,
                    "CodigoUsuario": 1,
                    "CodigoCaja": 1,
                    "Lineas": dest_order_lines,

                },

        }

        if zeta_conn.create_order(new_order):
            woo_conn.mark_order_as_synced(order)
            return True
        return False


def send_tracking_code_to_user(ecommerce_order: EcommerceOrder, tracking_code):
    """
    TODO:
    :param ecommerce_order:
    :param tracking_code:
    :return:
    """

    order = ecommerce_order.payload
    config = get_tenant_config(ecommerce_order.tenant)

    if not config.woocommerce_integration_enabled:
        raise Exception("Woocommerce integration disabled")

    woo_conn = WooCommerceAPI(url=config.woocommerce_site_url,
                              consumer_key=config.woocommerce_consumer_key,
                              consumer_secret=config.woocommerce_consumer_secret)

    woo_conn.inform_tracking_code(order, tracking_code)
    note = f'Tu pedido está en proceso, puedes rastrearlo aquí: https://www.dac.com.uy/envios/rastreo/Codigo_Rastreo/{tracking_code}'
    woo_conn.add_note_to_customer(order, note)


def send_order_to_dac_fulfillment(ecommerce_order: EcommerceOrder, tracking_code):
    """
    TODO:
    :param ecommerce_order:
    :param tracking_code:
    :return:
    """
    config = get_tenant_config(ecommerce_order.tenant)

    if not config.dac_integration_enabled:
        raise ValueError("DAC integration not enabled")

    if not config.woocommerce_integration_enabled:
        raise ValueError("Woocommerce integration not enabled")

    if not config.smtp_integration_enabled:
        raise ValueError("Email integration not enabled")

    woo_conn = WooCommerceAPI(url=config.woocommerce_site_url,
                              consumer_key=config.woocommerce_consumer_key,
                              consumer_secret=config.woocommerce_consumer_secret)

    order = ecommerce_order.payload

    if woo_conn.sent_to_dac(order):
        return "sent previously"

    else:
        shipping_method = get_shipping_method(order)

        if shipping_method in ["flat_rate", "free_shipping", "empty"]:

            billing = order["billing"]
            pedido = order["number"]
            first_name = billing.get("first_name", "")
            last_name = billing.get("last_name", "")

            address_2 = billing.get("address_2", "")
            email = billing.get("email", "")
            phone = billing.get("phone", "")
            comentarios = f'{address_2} - {order["customer_note"]}'

            flat_address = woo_conn.woo_address_formatted_for_dac(billing)
            if tracking_code is None:
                tracking_code = "Crear manualmente"

            html_body = f"""
                <html>
                    <body>
                        <h2>Datos de Envío</h2>
                        <p><strong>Guia:</strong> {tracking_code}</p>
                        <p><strong>Pedido:</strong> {pedido}</p>
                        <p><strong>Destinatario:</strong> {first_name} {last_name}</p>
                        <p><strong>Dirección:</strong> {flat_address}</p>
                        <p><strong>Notas adicionales:</strong> {comentarios}</p>
                        <p><strong>Email:</strong> {email}</p>
                        <p><strong>Celular:</strong> {phone}</p>
                        
                    </body>
                </html>
                """

            # Email details
            settings.EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
            settings.EMAIL_HOST = config.smtp_host
            settings.EMAIL_PORT = config.smtp_port
            settings.EMAIL_USE_TLS = config.smtp_use_tls
            settings.EMAIL_HOST_USER = config.smtp_user
            settings.EMAIL_HOST_PASSWORD = config.smtp_password
            settings.DEFAULT_FROM_EMAIL = config.smtp_from

            subject = f'Pedido {config.tenant.nombre}: {order["number"]} '
            html_content = html_body
            to = config.dac_notification_list.split(",")

            filename = f'Detalle_pedido_{order["number"]}.xlsx'
            excel_file = create_order_details_excel(order)

            # Create email message with attachment
            email = EmailMessage(subject, html_content, config.smtp_user, to)

            email.attach(filename, excel_file.read(), 'application/vnd.ms-excel')
            email.content_subtype = "html"

            # Send the email
            send_mail_result = email.send()

            woo_conn.mark_order_as_sent_to_process(order)

            return send_mail_result


def register_shipping_request(ecommerce_order: EcommerceOrder):

    order = ecommerce_order.payload
    woo_config = get_tenant_config(ecommerce_order.tenant)

    if not woo_config.woocommerce_integration_enabled:
        raise ValueError("WooCommerce Integration not enabled")

    shipping_method = get_shipping_method(order)
    billing = order["billing"]

    if shipping_method == "empty":
        delivery_type = "4"
    else:
        delivery_type = "2"

    try:
        shipping = Shipment.objects.get(order__exact=order["number"])

    except Shipment.DoesNotExist:

        print(f'Creando solicitud de envio para {order["number"]}')

        woo_conn = WooCommerceAPI(url=woo_config.woocommerce_site_url,
                                  consumer_key=woo_config.woocommerce_consumer_key,
                                  consumer_secret=woo_config.woocommerce_consumer_secret)

        address = woo_conn.woo_address_formatted_for_dac(billing)

        shipping = Shipment.objects.create(
            tenant=ecommerce_order.tenant,
            delivery_status="NUEVA SOLICITUD",
            recipient_name=f'{billing["first_name"]} {billing["last_name"]}',
            recipient_phone=billing["phone"],
            recipient_email=billing["email"],
            delivery_type=delivery_type,
            order=order["number"],
            comments=f'{billing["address_2"]} | {order["customer_note"]}',
            shipping_address=address,
            closed=False
            )

        shipping.save()

    print(f'Shipping for {order["number"]} was saved')
    return shipping


def import_zeta_products():
    pass


def import_woo_product(product, tenant):

    if product["type"] == "simple":

        attrs = {}

        for attr in product["attributes"]:
            attrs[attr["name"]] = attr["options"]

        new_prod = {
            "name": product["name"],
            "description": product["description"],
            "price": get_product_price(product),
            "sale_price": get_product_sale_price(product),
            "brand": get_product_brand(product),
            "sku": product["sku"],
            "product_type": "STD",
            "category": get_product_category(product),
            "tenant": tenant,
            "permalink": product["permalink"],
            "main_image": get_product_main_image(product),
            "frontend_product_id": product["id"],
            "attributes": attrs
        }

        try:
            p = Product.objects.get(sku=product["sku"], tenant=tenant)
            p.name = product["name"]
            p.description = new_prod["description"]
            p.price = new_prod["price"]
            p.sale_price = new_prod["sale_price"]
            p.brand = new_prod["brand"]
            p.category = new_prod["category"]
            p.permalink = new_prod["permalink"]
            p.main_image = new_prod["main_image"]
            p.frontend_product_id = new_prod["frontend_product_id"]
            p.attributes = new_prod["attributes"]
            p.save()

        except Product.MultipleObjectsReturned:

            p = Product.objects.filter(sku=product["sku"], tenant=tenant).first()

            for pr in Product.objects.filter(sku=product["sku"], tenant=tenant).exclude(id=p.id):
                pr.delete()

        except Product.DoesNotExist:
            p = Product.objects.create(**new_prod)
            p.save()

        # assign tags
        tags = []
        for woo_tag in get_product_tags(product):
            try:
                tag = Tag.objects.get(name__exact=woo_tag["name"], tenant=tenant, context="product")
                tags.append(tag)

            except Tag.DoesNotExist:
                tag = Tag.objects.create(slug=woo_tag["slug"], name=woo_tag["name"], tenant=tenant, context="product")
                tag.save()
                tags.append(tag)

            except Exception as e:
                print(e)

        # Assign tags to the product

        p.tags.set(tags)
        p.save()
        logger.info('%s was imported', p.name)

    else:
        logger.warning(f'Import of %s products not implemented yet', product["type"])


def import_dac_delivery_status():

    from tenancy.models import Tenant
    for tenant in Tenant.objects.all():
        tenant_configuration = get_tenant_config(tenant)

        if tenant_configuration.dac_integration_enabled:
            print(f"Checking DAC {tenant_configuration.tenant} deliveries...")

            dac_conn = DacApi(
                url=tenant_configuration.dac_base_url,
                user=tenant_configuration.dac_user,
                password=tenant_configuration.dac_password
            )

            # Get the current time (now)
            end_date = timezone.now()
            start_date = end_date - timedelta(days=tenant_configuration.dac_tracking_period)
            formatted_start_date = start_date.strftime('%Y-%m-%d')
            formatted_end_date = end_date.strftime('%Y-%m-%d')

            # Call the function with formatted dates
            guias = dac_conn.mis_guias(fecha_inicio=formatted_start_date, fecha_fin=formatted_end_date, rut=tenant_configuration.dac_rut)

            for item in guias:

                # Parse the datetime string into a naive datetime object
                naive_datetime = datetime.strptime(item["F_Documentacion"], "%m/%d/%Y %I:%M:%S %p")

                # Assuming you want to convert this datetime to the current timezone set in Django settings
                f_registro = timezone.make_aware(naive_datetime, timezone.get_current_timezone()).strftime(
                    "%Y-%m-%d %H:%M:%S %Z")

                try:  # actualizar guia

                    current_shipment = Shipment.objects.get(shipping_code=item["K_Guia"], tenant=tenant_configuration.tenant)

                    print(item['D_Estado_Guia'])
                    try:
                        print(f'Updating {item["K_Guia"]}')
                        current_shipment.delivery_status = item['D_Estado_Guia']
                        current_shipment.shipping_origin = item["D_Oficina_Origen"]
                        current_shipment.shipping_type = item["D_Tipo_Envio"]
                        current_shipment.shipping_date = f_registro
                        current_shipment.shipping_invoice = item["K_Factura"]
                        current_shipment.shipping_condition = item["D_Tipo_Guia"]
                        current_shipment.shipping_notes = item["Observaciones"]
                        current_shipment.delivery_type = item["D_Tipo_Entrega"]
                        current_shipment.delivery_status = item["D_Estado_Guia"]
                        current_shipment.recipient_phone = item["Telefono_Destinatario"]

                        if item['D_Estado_Guia'] == "ENTREGADA" and not current_shipment.closed:
                            current_shipment.closed = True
                            current_shipment.closed_date = timezone.now()
                            close_order(current_shipment)

                        current_shipment.save()

                    except Exception as e:
                        print(e)

                except Shipment.DoesNotExist:
                    try:
                        notas = item["Observaciones"]
                        order_number = notas.split("-")[0].strip()
                        print(f"Order from observaciones: {order_number}")
                        current_shipment = Shipment.objects.get(order=order_number, tenant=tenant_configuration.tenant)
                        current_shipment.shipping_code = item["K_Guia"]
                        current_shipment.save()

                    except Exception as e:

                        if item['D_Estado_Guia'] != "CANCELADA":
                            print(f'Registering {item["K_Guia"]}')
                            new_shipping_record = Shipment.objects.create(
                                shipping_origin=item["D_Oficina_Origen"],
                                shipping_code=item["K_Guia"],
                                shipping_type=item["D_Tipo_Envio"],
                                shipping_date=f_registro,
                                shipping_invoice=item["K_Factura"],
                                shipping_condition=item["D_Tipo_Guia"],
                                shipping_notes=item["Observaciones"],
                                delivery_type=item["D_Tipo_Entrega"],
                                delivery_status=item["D_Estado_Guia"],
                                recipient_name=item["Destinatario"],
                                recipient_phone=item["Telefono_Destinatario"],
                                closed=False,
                                tenant=tenant_configuration.tenant
                            )
                            new_shipping_record.save()

                except Shipment.MultipleObjectsReturned:
                    print("Multiples guias repetidas")

            dac_conn.end_session()

        else:
            print(f"DAC Integration disabled for {tenant_configuration.tenant}")


def close_order(shipment: Shipment):
    tenant_configuration = get_tenant_config(shipment.tenant)

    if tenant_configuration.woocommerce_integration_enabled:
        woo_conn = WooCommerceAPI(
            url=tenant_configuration.woocommerce_site_url,
            consumer_key=tenant_configuration.woocommerce_consumer_key,
            consumer_secret=tenant_configuration.woocommerce_consumer_secret
        )
        try:
            if not shipment.order:
                notas = shipment.shipping_notes
                order_number = notas.split("-")[0].strip()
                print(f"Order from observaciones: {order_number}")
            else:
                order_number = shipment.order

            order = woo_conn.get_order(order_number)
            if order:
                shipment.order = order["number"]
                shipment.save()
                woo_conn.mark_as_completed(order)
                print(f"Marcando {shipment.order} como completada")

        except Exception as e:
            print(f"No se conoce la orden de la guia {shipment.shipping_code}")


def import_woo_order_items(order, line_items):

    for item in line_items:
        new_item = EcommerceOrderLine(
            sku=item["sku"],
            sale_price=item["price"],
            order_qty=item["quantity"],
            line_total=item["total"],
            line_tax=item["total_tax"],
            line_subtotal=0,
            line_discount=0,
            line_currency=0,
            order=order
            )
        new_item.save()


def process_shipping_address(shipping):

    """
    'shipment': {'first_name': 'Maria', 'last_name': 'Alvarez', 'company': '', 'address_1': 'Pablo rios 341', 'address_2': 'apto 102', 'city': 'Tacuarembo', 'state': 'UY-TA', 'postcode': '45000', 'country': 'UY', 'phone': '094931814'}

    """
    pass


def process_woo_shipping_lines(shipping_lines):
    """
    'shipping_lines': [
    {'id': 721, 'method_title': 'Shipping', 'method_id': 'free_shipping', 'instance_id': '0', 'total': '0', 'total_tax': '0', 'taxes': [{'id': 1, 'total': '0', 'subtotal': ''}], 'meta_data': []}
    ],
    """
    pass


def process_woo_tax_lines(tax_lines):
    """
    'tax_lines': [
    {'id': 719, 'rate_code': 'UY-IVA-1', 'rate_id': 1, 'label': 'IVA', 'compound': False, 'tax_total': '2153', 'shipping_tax_total': '0', 'rate_percent': 22, 'meta_data': []}
    ],
    """
    pass


def process_woo_order_meta_data(metadata):
    """
    'meta_data': [
                {'id': 2446, 'key': '_automatewoo_order_created', 'value': '1'},
                {'id': 2445, 'key': 'mailchimp_woocommerce_landing_site', 'value': 'https://andressa.com.uy/'},
                {'id': 2451, 'key': 'sent_to_dac', 'value': 'true'},
                {'id': 2450, 'key': 'synced', 'value': 'true'}
                ],
    """


def process_woo_order_fee_lines(fee_lines):
    """
    'fee_lines': [],
    """
    pass


def process_woo_order_refunds(refunds):
    """
    'refunds':[],
    """
    pass


def process_woo_order_coupon_lines(coupon_lines):
    """
    'coupon_lines': [],
    """
    pass


# Order Import from Woocommerce
def register_or_update_ecommerce_order(payload, tenant):

    customer_registered_address = {
        "billing": payload["billing"],
        "shipping": payload["shipping"],
        "notes": payload["customer_note"],
        "shipping_details": payload["shipping_lines"]
    }

    naive_datetime = datetime.strptime(payload["date_created"], "%Y-%m-%dT%H:%M:%S")
    created = timezone.make_aware(naive_datetime, timezone.get_default_timezone())

    naive_datetime = datetime.strptime(payload["date_modified"], "%Y-%m-%dT%H:%M:%S")
    modified = timezone.make_aware(naive_datetime, timezone.get_default_timezone())
    try:
        total = float(payload["total"])
    except Exception as e:
        total = 0
        print(e)

    try:
        order = EcommerceOrder.objects.get(order_number__exact=payload["number"], tenant=tenant)

        order.order_number = payload["number"]
        order.status = payload["status"]
        order.created = created
        order.modified = modified
        # created = timezone.now,
        order.customer_name = f'{payload["billing"]["first_name"]} {payload["billing"]["last_name"]}'
        order.customer_phone = f'{payload["billing"]["phone"]}'.strip().replace(" ", "")
        order.customer_email = f'{payload["billing"]["email"]}'.strip().replace(" ", "")
        order.order_customer_registered_address = customer_registered_address
        order.payload = payload
        order.total = total

        # payload["created_via"]

    except EcommerceOrder.DoesNotExist:

        order = EcommerceOrder(
            order_number=payload["number"],
            status=payload["status"],
            tenant=tenant,
            created=created,
            modified=modified,
            customer_name=f'{payload["billing"]["first_name"]} {payload["billing"]["last_name"]}',
            customer_phone=f'{payload["billing"]["phone"]}'.strip().replace(" ", ""),
            customer_email=f'{payload["billing"]["email"]}'.strip().replace(" ", ""),
            order_customer_registered_address=customer_registered_address,
            payload=payload,
            total=total
            # payload["created_via"]
        )

    order.save()
    return order


def get_all_orders(tenant=None):

    if tenant is None:
        config_iter = iter_configs_with_integration_enabled("woocommerce")
    else:
        config_iter = [(tenant, get_tenant_config(tenant))]

    for _t, tenant_configuration in config_iter:
        if tenant_configuration.woocommerce_integration_enabled:
            woo_conn = WooCommerceAPI(url=tenant_configuration.woocommerce_site_url, consumer_key=tenant_configuration.woocommerce_consumer_key, consumer_secret=tenant_configuration.woocommerce_consumer_secret)
            orders = woo_conn.get_orders()
            for order in orders:
                print(f'Processing order {order["number"]}')
                register_or_update_ecommerce_order(order, tenant_configuration.tenant)


def create_location(customer, billing):
    new_location = Address(
        customer=customer,
        name=billing["address_1"],
        address=billing["address_1"],
        address_internal=billing["address_2"],
        city=billing["city"],
        state=billing["state"],
        country=billing["country"],
        postalcode=billing["postcode"],
        invoice_address=True,
        delivery_address=True,
        enabled=True
    )
    new_location.save()
