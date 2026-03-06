import io
from datetime import timedelta

import pandas as pd
from django.utils import timezone

from crm.lib.dac_api import DacApi
from portal.models import TenantConfiguration


def generate_fecha_levante():
    # Get the current date and time in the project's timezone
    current_datetime = timezone.now()

    # Set the target time (6:00 PM) in the project's timezone
    target_time = current_datetime.replace(hour=18, minute=0, second=0, microsecond=0)

    # Check if the current time is before the target time
    if current_datetime < target_time:
        # If before 6 PM, keep the current date and set the time to 18:00:00
        result_datetime = target_time
    else:
        # If after 6 PM, add one day and set the time to 18:00:00
        next_day_datetime = current_datetime + timedelta(days=1)
        result_datetime = next_day_datetime.replace(hour=18, minute=0, second=0, microsecond=0)

    # Format the result as a string
    formatted_result = result_datetime.strftime('%Y/%m/%d %H:%M:%S')

    return formatted_result


def create_order_details_excel(order):
    dest_order_lines = []
    order_items = order["line_items"]
    for item in order_items:
        dest_order_item = {
            "Articulo": item["sku"],
            "Destino": "",
            "Cantidad": item["quantity"],
            "Justificacion": order["number"],
            "Pedido": order["number"],
            "Tipo": "3"
        }
        dest_order_lines.append(dest_order_item)

    df = pd.DataFrame(dest_order_lines)
    # Save DataFrame to an Excel file in memory
    excel_file = io.BytesIO()
    with pd.ExcelWriter(excel_file, engine='openpyxl') as writer:
        df.to_excel(writer, index=False)
    excel_file.seek(0)  # Go to the beginning of the file

    return excel_file


def get_shipping_method(order):

    if len(order["shipping_lines"]) > 0:
        return order["shipping_lines"][0].get("method_id", "empty")

    else:
        return "empty"


def moio_order_router(woo_conn):

    instructions = """Este es un paquete de datos de un pedido que hay que entregar.
    Analizar la informacion, si la direccion de facturacion es igual a la de envio o si la de envio esta vacia se debe usar la de facturacion, 
    de lo contrario se usa la de envio y crear una dirección y decidir si se debe enviar o no (solo se envia en status processing), 
    entregar un formato json que conste de 
    Nombre completo
    Numero de pedido
    Direccion (calle y numero,barrio, ciudad, pais en una linea ej: Vilardebo 1265,Reducto,Montevideo,Uruguay) 
    Notas adicionales (cualquier aclaracion adicional a la direccion, especialmente informacion excesiva del campo direccion )  , 
    Acciones, 
    Tipo de Envio (retirar en agencia, envio a domicilio, retirar en local)"""

    orders = woo_conn.get_orders()

    for order in orders:

        shipping_data = {

            "order": order["number"],
            "date": order["date_modified"],
            "billing": order["billing"],
            "billing_address": woo_conn.woo_address_formatted_for_dac(order["billing"]),
            #"shipping_address": woo_conn.woo_address_formatted_for_dac(order["shipping"]),
            "shipping_method": get_shipping_method(order),
            "notes": order["customer_note"],
            "status": order["status"]


        }

        prompt = f'{instructions} {shipping_data}'
        # response = get_json_response(prompt=prompt, model="gpt-4-1106-preview")


def create_dac_delivery(delivery_request):

    dac_config = TenantConfiguration.objects.get(tenant=delivery_request.tenant)

    if not dac_config.dac_integration_enabled:
        return None

    dac_conn = DacApi(url=dac_config.dac_base_url, user=dac_config.dac_user,
                      password=dac_config.dac_password)

    try:
        delivery_response = dac_conn.new_delivery(
            nombre_rte=dac_config.dac_sender_name,
            fecha_levante=generate_fecha_levante(),
            telefono_rte=dac_config.dac_sender_phone,
            codigo_dom_recoleccion="",
            nombre_dest=delivery_request.recipient_name,
            domicilio_dest=delivery_request.shipping_address,
            documento_dest=delivery_request.recipient_email,
            telefono_dest=delivery_request.recipient_phone,
            notas=delivery_request.comments,
            tipo_guia=delivery_request.delivery_type,
            ref_pedido=f'{dac_config.tenant.nombre}-{delivery_request.order}'
        )

        print(f'delivery response: {delivery_response}')

        delivery_request.shipping_code = delivery_response["K_Guia"].replace("-", "")
        delivery_request.tracking_code = delivery_response["Codigo_Rastreo"]
        delivery_request.save()
        dac_conn.end_session()

        return delivery_request.tracking_code

    except Exception as e:
        dac_conn.end_session()
        print(f'Error: {e}')
        return None



