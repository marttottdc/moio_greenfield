import json

from central_hub.models import TenantConfiguration
from chatbot.lib.whatsapp_client_api import WhatsappBusinessClient, get_template, compose_template_based_message, template_requirements


config = TenantConfiguration.objects.get(tenant_id=1)


wa_client = WhatsappBusinessClient(config)


try:
    wa_client.retrieve_template_namespace()

except Exception as e:
    print(e)

try:

    templates = wa_client.download_message_templates()

    print(f"Found {len(templates)} templates")
    print("-----------------------------------")

    for t in templates:
        print(t["name"], t["status"])

    print("------------------------------------------------------")

    selection = input("Which template would you like to use? ")
    selected_template = get_template(templates, selection)

    print(f"Selected spec: {selected_template}")

    message_template_namespace = wa_client.retrieve_template_namespace()

    print(f"namespace: {message_template_namespace}")
    phone = input("Which phone would you like to use? ")

    print(f'selected template: {selected_template["name"]}')
    print(f'Components: {selected_template["components"]}')

    # requirements = template_requirements(selected_template)
    # print(requirements)

    # Hay que armar un paquete de datos así para proveer los datos necesarios según los requerimientos de cada template.
    # Si sabemos que template vamos a user, podemos saber que datos necesita.

    # Hacer la modification para que funcione con NAMED PARAMETERS
    # Terminar el composer para mensajes interactivos

    kwargs = {
        "header_image_URL": "https://moiodigital.com/wp-content/uploads/2024/09/Diseno-sin-titulo-30.png",
        "1": "Pepe",
        "2": "Moio",
        "3": "Nuestro Servicio"

    }
    wa_client.template_details(selected_template["id"])

    requirements = template_requirements(selected_template)
    print(f'Requirements: {requirements}')

    # components = setup_template_components(selected_template, **requirements)

    # requirements = template_components(selected_template, **kwargs)

#    msg = compose_template_based_message(selected_template, phone=phone, namespace=message_template_namespace, components=requirements)

 #   if not wa_client.send_message(msg):

  #      print(f'message_data": {msg}')

    # Cuando mandemos mensajes salientes lo haremos a contactos sin sesiones activas.
    # Si la session esta activa, se espera a que se cierre
    # Se creará una nueva session insertando el mensaje del template en un nuevo thread
    # se asignará el contacto y el assistant ID pero no se ejecutará el thread
    # Probablemente se pueda alterar las instrucciones para instruir al asistente como proceder.

except Exception as e:
    print(e)


