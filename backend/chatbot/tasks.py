import asyncio
import json
import logging
import os
from django.conf import settings
import requests
from celery._state import current_task
from celery import shared_task, group
from django.core.exceptions import ImproperlyConfigured
from django.utils import timezone

from chatbot.core.chatbot import Chatbot, MoioAssistant
from chatbot.core.moio_agent import MoioAgent, AgentEngine
from chatbot.lib.whatsapp_client_api import WhatsappMessage, WhatsappWebhook, WhatsappBusinessClient
from chatbot.core.messenger import Messenger
from chatbot.core.email_utils import sync_email_account

from crm.models import Contact

from moio_platform.lib.openai_gpt_api import whisper_to_text, image_reader
from central_hub.models import PlatformConfiguration
from central_hub.integrations.models import IntegrationConfig
from central_hub.tenant_config import (
    get_tenant_config,
    get_tenant_config_by_id,
    get_tenant_config_for_integration_instance,
    get_whatsapp_integration_by_asset_ids,
    iter_configs_with_integration_enabled,
)
from tenancy.context_utils import current_tenant
from tenancy.models import Tenant
from tenancy.tenant_support import tenant_rls_context
from chatbot.models.email_data import EmailMessage, EmailAccount
from chatbot.models.wa_payloads import WaPayloads
from moio_platform.lib.tools import check_elapsed_time, has_time_passed

from chatbot.models.agent_session import AgentSession
from chatbot.core.moio_agent import MoioAgent
from crm.services.contact import get_contact_by_phone, is_blacklisted_contact

# Get an instance of a logger
logger = logging.getLogger(__name__)


def _human_mode_inbound_content(received_whatsapp: WhatsappMessage) -> str:
    inbound_content = getattr(received_whatsapp, "msg_content", None)
    if inbound_content in (None, ""):
        inbound_content = getattr(received_whatsapp, "raw_message", None)
    if inbound_content in (None, ""):
        inbound_content = getattr(received_whatsapp, "content_type", "")

    if isinstance(inbound_content, str):
        return inbound_content

    try:
        return json.dumps(inbound_content, ensure_ascii=False)
    except (TypeError, ValueError):
        return str(inbound_content)


def preprocess_message(received_whatsapp, config):

    wa = WhatsappBusinessClient(config)

    message = {
        "content": "",
        "type": received_whatsapp.content_type,
        "read": True,
        "error": False,
        "msg_id": received_whatsapp.msg_id,
        "original_content": received_whatsapp.msg_content,
        "context": ""
    }

    if received_whatsapp.is_message():

        if received_whatsapp.content_is_text():
            # contestar a un simple texto
            message["content"] = received_whatsapp.get_message_text()

            if received_whatsapp.get_context():
                message["content"] = received_whatsapp.get_message_text()
                message["context"] = json.dumps(received_whatsapp.get_context())

        elif received_whatsapp.content_is_audio():

            audio_path = wa.download_media(received_whatsapp.get_media_id())
            message["media"] = audio_path

            if audio_path is not None:

                received_text = whisper_to_text(
                    audio_path,
                    openai_api_key=config.openai_api_key
                )

                message["content"] = received_text

                if received_text is None:
                    message["error"] = True
            else:
                message["error"] = True

        elif received_whatsapp.content_is_video():

            video_path = wa.download_media(received_whatsapp.get_media_id())
            message["media"] = video_path
            message["error"] = True

        elif received_whatsapp.content_is_document():

            doc_path = wa.download_media(received_whatsapp.get_media_id())
            message["media"] = doc_path
            message["error"] = True

        elif received_whatsapp.content_is_image():

            image_path = wa.download_media(received_whatsapp.get_media_id(), return_url=True)
            message["media"] = image_path

            instruction = "describe la imagen"

            try:
                image_description = image_reader(
                    image_path,
                    instruction,
                    openai_api_key=config.openai_api_key,
                    model=config.openai_default_model
                )
                message["content"] = f"El usuario envio una imagen con este contenido:{image_description} y este caption {received_whatsapp.get_caption()}"

            except Exception as e:
                message["error"] = True

        elif received_whatsapp.content_is_reaction():

            message["content"] = f"Usuario dice: {received_whatsapp.get_emoji()} -> Read"
            message["media"] = received_whatsapp.get_emoji()

        elif received_whatsapp.content_is_location():

            location = received_whatsapp.msg_content

            user_location = {
                "latitude": location["latitude"],
                "longitude": location["longitude"]
            }

            message["content"] = f'user location:{json.dumps(user_location)}'

        elif received_whatsapp.content_is_button():
            message["content"] = received_whatsapp.get_button_payload()

        elif received_whatsapp.content_is_interactive():
            message["content"] = received_whatsapp.get_content()

        elif received_whatsapp.content_is_order():
            message["content"] = received_whatsapp.get_order_content()

        elif received_whatsapp.content_is_contact():
            message["content"] = received_whatsapp.get_contact_data()

        else:

            message = {
                "content": received_whatsapp.display_message(),
            }

    return message


def process_message_with_assistant(received_whatsapp: WhatsappMessage, config):
    start_time = timezone.now()
    logger.info("Starting message Processing with Assistant: %s", received_whatsapp.msg_id)

    wa = WhatsappBusinessClient(config)

    if received_whatsapp.is_message():

        logger.info("Retrieving Contact to process: %s", received_whatsapp.msg_id)
        whatsapp_name = received_whatsapp.get_contact_name()
        phone = received_whatsapp.get_contact_number()

        contact = get_contact_by_phone(phone, whatsapp_name, config)
        if getattr(contact, "is_blacklisted", False):
            logger.info("Skipping assistant reply: contact is blacklisted (%s)", contact.phone)
            try:
                wa.mark_as_read(received_whatsapp.msg_id)
            except Exception:
                logger.exception("Failed to mark blacklisted message as read")
            return

        logger.info("Retrieving Assistant Data message to process: %s", received_whatsapp.msg_id)

        assistant = MoioAssistant(
            openai_key=config.openai_api_key,
            contact=contact,
            tenant_id=config.tenant_id,
            default_assistant_id=config.assistants_default_id,
            channel="whatsapp"
        )
        reply = None
        logger.info(check_elapsed_time(start_time, "Time from Start Ready"))

        if received_whatsapp.content_is_text():
            # contestar a un simple texto
            received_text = received_whatsapp.get_message_text()

            if received_whatsapp.get_context():
                context_text = json.dumps(received_whatsapp.get_context())
                received_text = f'{received_text} {context_text}'

            wa.mark_as_read(received_whatsapp.msg_id)
            print(f'Usuario dice: {received_text} -> Read')

            reply = assistant.reply_to_this(message_content=received_text)
            logger.debug(reply)

        elif received_whatsapp.content_is_audio():

            audio_path = wa.download_media(received_whatsapp.get_media_id())

            if audio_path is not None:

                received_text = whisper_to_text(audio_path, openai_api_key=config.openai_api_key)

                if received_text is not None:

                    wa.mark_as_read(received_whatsapp.msg_id)
                    print(f'Usuario dice: {received_text} -> Read')

                    reply = assistant.reply_to_this(message_content=received_text)
                else:
                    reply = "No entendí el mensaje, me podrías escribir el mensaje ?"
            else:
                reply = "No entendí el mensaje, me podrías escribir el mensaje ?"

        elif received_whatsapp.content_is_video():
            video_path = wa.download_media(received_whatsapp.get_media_id())
            print(f'Video recibido {video_path}')
            # Do something with the video, process and create a reply

            reply = "No puedo entender videos aun, me podrías escribir el mensaje ?"

        elif received_whatsapp.content_is_image():

            image_path = wa.download_media(received_whatsapp.get_media_id(), return_url=True)

            print(f'Imagen recibida {image_path}')

            instruction = "describe la imagen"
            try:
                image_description = image_reader(image_path, instruction, openai_api_key=config.openai_api_key, model=config.openai_default_model)

            except Exception as e:
                image_description = " "

            received_input = f"El usuario envio una imagen con este contenido:{image_description} y este caption {received_whatsapp.get_caption()}"

            if received_input is not None:
                wa.mark_as_read(received_whatsapp.msg_id)
                print(f'Usuario dice: {received_input} -> Read')
                reply = assistant.reply_to_this(message_content=received_input)

        elif received_whatsapp.content_is_reaction():

            wa.mark_as_read(received_whatsapp.msg_id)
            print(f'Usuario dice: {received_whatsapp.get_emoji()} -> Read')
            reply = assistant.reply_to_this(received_whatsapp.get_emoji())

        elif received_whatsapp.content_is_location():
            location = received_whatsapp.msg_content

            user_location ={
                "latitude": location["latitude"],
                "longitude": location["longitude"]
            }

            received_text = f'user location:{json.dumps(user_location)}'
            wa.mark_as_read(received_whatsapp.msg_id)
            print(f'Usuario dice: {received_text} -> Read')

            reply = assistant.reply_to_this(message_content=received_text)

        elif received_whatsapp.content_is_interactive():

            wa.mark_as_read(received_whatsapp.msg_id)
            print(f'Usuario dice: {received_whatsapp.get_interactive_content()} -> Read')

            reply = assistant.reply_to_this(message_content=received_whatsapp.get_interactive_content())

        elif received_whatsapp.content_is_order():
            wa.mark_as_read(received_whatsapp.msg_id)
            print(f'Usuario envio un pedido -> Read')
            reply = assistant.reply_to_this(message_content=received_whatsapp.get_order_content())

        else:
            wa.mark_as_read(received_whatsapp.msg_id)
            print(f'Usuario dice: {received_whatsapp.content_type}, -> Read')
            print(received_whatsapp.display_message())
            reply = f'no se interpretar {received_whatsapp.content_type}, me lo puedes escribir ?'

        # Send the Reply to the Contact
        moio_messenger = Messenger(channel=assistant.channel, config=config, client_name="assistant")
        logger.info("Done Processing Message %s", received_whatsapp.msg_id)
        human_mode_enabled = bool(getattr(assistant.assistant_session, "human_mode", False))

        if human_mode_enabled:
            if reply is not None:
                # Persist inbound content in human mode even for fallback branches.
                assistant.reply_to_this(message_content=_human_mode_inbound_content(received_whatsapp))
            logger.info("Human mode enabled - skipping automated assistant reply for session %s", assistant.assistant_session.pk)
        elif config.assistant_smart_reply_enabled and reply is not None:
            send_message_time = timezone.now()

            if assistant.get_response_format() == "text":
                if moio_messenger.smart_reply(reply, contact.phone):
                    logger.error(check_elapsed_time(start_time, "Time from Start to message"))
                    logger.error(check_elapsed_time(send_message_time, "Send Message Took"))
                else:
                    logger.error("Could not send structured message, trying just_reply")
                    moio_messenger.just_reply(reply, contact.phone)

            elif assistant.get_response_format() == "json_schema":
                if moio_messenger.structured_reply(reply, contact.phone):
                    logger.error(check_elapsed_time(start_time, "Time from Start to message"))
                    logger.error(check_elapsed_time(send_message_time, "Send Message Took"))
                else:
                    logger.error("Could not send structured message, trying just_reply")
                    moio_messenger.just_reply(reply, contact.phone)

        else:
            moio_messenger.just_reply(reply, contact.phone)

        logger.info("Processing message for %s", config.whatsapp_name)
    else:
        logger.info("Processing update for %s", config.whatsapp_name)

        received_whatsapp.display_message()

    logger.info(check_elapsed_time(start_time, "Process_message_with_assistant"))

    try:
        wa.register_message(received_whatsapp)
        logger.info("Message registered")
    except Exception as e:
        logger.error(e)


def process_message_with_chatbot(received_whatsapp: WhatsappMessage, config):

    wa = WhatsappBusinessClient(config)

    if received_whatsapp.is_message():

        whatsapp_name = received_whatsapp.get_contact_name()
        number = received_whatsapp.get_contact_number()
        # Crear el usuario a partir de los datos del mensaje recibido
        contact = Contact.create_or_update(phone=number,
                                           whatsapp_name=whatsapp_name,
                                           tenant=config.tenant,
                                           source="chatbot")
        if contact is None:
            logger.error("Could not create/update contact for number %s; skipping reply", number)
            try:
                wa.mark_as_read(received_whatsapp.msg_id)
            except Exception:
                logger.exception("Failed to mark message as read after contact error")
            return
        if getattr(contact, "is_blacklisted", False):
            logger.info("Skipping chatbot reply: contact is blacklisted (%s)", contact.phone)
            try:
                wa.mark_as_read(received_whatsapp.msg_id)
            except Exception:
                logger.exception("Failed to mark blacklisted message as read")
            return

        reply = "Tenemos problemas técnicos, intenta mas tarde por favor"
        chatbot = None
        chatbot_session = (
            AgentSession.objects.filter(
                contact=contact,
                active=True,
                tenant=config.tenant,
                channel="whatsapp",
            )
            .order_by("-last_interaction")
            .first()
        )
        chatbot_human_mode = bool(getattr(chatbot_session, "human_mode", False))

        if received_whatsapp.content_is_text():
            received_text = received_whatsapp.get_message_text()
            if chatbot is None:
                chatbot = Chatbot(contact=contact, channel="whatsapp", tenant=config.tenant)

            wa.mark_as_read(received_whatsapp.msg_id)
            print(f'Usuario dice: {received_text} -> ✅')

            reply = chatbot.reply_to_this(received_text)

        elif received_whatsapp.content_is_audio():
            if chatbot is None:
                chatbot = Chatbot(contact=contact, channel="whatsapp", tenant=config.tenant)
            # chatbot = Receptionist(contact=contact, channel="whatsapp")
            audio_path = wa.download_media(received_whatsapp.get_media_id())
            if audio_path is not None:
                received_text = whisper_to_text(audio_path, openai_api_key=config.openai_api_key)

                if received_text is not None:
                    reply = chatbot.reply_to_this(received_text)
                else:
                    reply = "no puedo procesar audios aun, me podrías escribir el mensaje ?"

        elif received_whatsapp.content_is_video():
            video_path = wa.download_media(received_whatsapp.get_media_id(),return_url=True)
            print(f'Video recibido {video_path}')
            reply = "no puedo procesar videos aun, me podrías escribir el mensaje ?"

        elif received_whatsapp.content_is_image():
            image_path = wa.download_media(received_whatsapp.get_media_id(), return_url=True)
            print(f'Imagen recibida {image_path}')
            instruction = "describe la imagen"

            if received_whatsapp.get_caption() != "":
                instruction = received_whatsapp.get_caption()

            resultado = image_reader(image_path, instruction, openai_api_key=config.openai_api_key)
            print(resultado)
            reply = f"Test de procesamiento de imagenes:  *{resultado}*"

        elif received_whatsapp.content_is_reaction():
            if chatbot is None:
                chatbot = Chatbot(contact=contact, channel="whatsapp", tenant=config.tenant)
            reply = chatbot.reply_to_this(f'el usuario respondio con una reaccion: {received_whatsapp.get_emoji()}')
            print(received_whatsapp.get_emoji())

        elif received_whatsapp.content_is_location():
            location = received_whatsapp.get_location()
            reply = "no puedo procesar ubicaciones aun, me podrías escribir el mensaje ?"
        else:
            reply = f'no se interpretar {received_whatsapp.content_type}, me lo puedes escribir ?'

        if chatbot is not None:
            chatbot_human_mode = bool(getattr(getattr(chatbot, "session", None), "human_mode", False))

        if chatbot_human_mode:
            if reply is not None:
                # Persist inbound content in human mode even for fallback branches.
                if chatbot is None:
                    chatbot = Chatbot(contact=contact, channel="whatsapp", tenant=config.tenant)
                chatbot.reply_to_this(_human_mode_inbound_content(received_whatsapp))
            logger.info("Human mode enabled - skipping automated chatbot reply for contact %s", contact.phone)
        else:
            # Send the Reply to the Contact
            moio_messenger = Messenger(channel="whatsapp", config=config, client_name="chatbot")
            moio_messenger.smart_reply(reply, contact.phone)


def process_message_with_agent(received_whatsapp: WhatsappMessage, config):
    start_time = timezone.now()
    logger.info("Starting message Processing with Agent: %s", received_whatsapp.msg_id)

    wa = WhatsappBusinessClient(config)

    if received_whatsapp.is_message():
        whatsapp_name = received_whatsapp.get_contact_name()

        logger.info("Retrieving Contact")

        phone = received_whatsapp.get_contact_number()
        contact = get_contact_by_phone(phone, whatsapp_name, config)
        if getattr(contact, "is_blacklisted", False):
            logger.info("Skipping agent reply: contact is blacklisted (%s)", contact.phone)
            try:
                wa.mark_as_read(received_whatsapp.get_msg_id())
            except Exception:
                logger.exception("Failed to mark blacklisted message as read")
            return

        print(f"Contacto {contact.fullname} | Tipo de contacto {contact.ctype} | Creado {contact.created}")

        agent = AgentEngine(config, contact)
        message = preprocess_message(received_whatsapp, config)
        if message["read"]:
            wa.mark_as_read(received_whatsapp.get_msg_id())
            reply = agent.reply_to_message(message)

        else:
            reply = "Error"

        human_mode_enabled = bool(getattr(agent.assistant_session, "human_mode", False))
        if human_mode_enabled:
            logger.info("Human mode enabled - skipping automated agent reply for session %s", agent.assistant_session.pk)
        else:
            if not reply:
                reply = "Error"

            # Send the Reply to the Contact
            moio_messenger = Messenger(channel=agent.channel, config=config, client_name="agent")

            if type(reply) is not str:
                reply = reply.model_dump()

            # moio_messenger.structured_reply(reply, contact.phone)
            # moio_messenger.smart_reply(reply, contact.phone)

            moio_messenger.just_reply(reply, contact.phone)

        logger.info("Done Processing Message %s", received_whatsapp.msg_id)
        logger.info("Processing message for %s", config.whatsapp_name)

    else:
        logger.info("Processing update for %s", config.whatsapp_name)
        received_whatsapp.display_message()
    logger.info(check_elapsed_time(start_time, "Process_message_with_assistant"))

    try:
        wa.register_message(received_whatsapp)
        logger.info("Message registered")
    except Exception as e:
        logger.error(e)


def redirect_webhook(url, body):

    headers = {'Content-Type': 'application/json'}
    response = requests.post(url, headers=headers, json=body)

    # Log the forwarding response (optional)
    print(f"Forwarded webhook response: {response.status_code}")


@shared_task(bind=True, queue=settings.LOW_PRIORITY_Q)
def heartbeat(self):

    task_id = current_task.request.id
    q_name = self.request.delivery_info['routing_key']
    logger.info(f'Processing chatbot heartbeat ---> {task_id} from {q_name}')


@shared_task(bind=True, queue=settings.MEDIUM_PRIORITY_Q)
def session_sweeper(self):
    task_id = current_task.request.id
    q_name = self.request.delivery_info['routing_key']
    logger.info(f'Processing chatbot heartbeat ---> {task_id} from {q_name}')
    
    for _tenant, config in iter_configs_with_integration_enabled("whatsapp"):
        sessions = AgentSession.objects.filter(
            tenant_id=config.tenant_id,
            active=True,
            channel="whatsapp"
        ).select_related("contact").iterator()

        for session in sessions:
            if has_time_passed(session.last_interaction, config.assistants_inactivity_limit):
                try:
                    engine = AgentEngine(config, session.contact)
                    reply = engine.analyze_conversation("Conversation is inactive – consider ending it")
                    if reply:
                        messenger = Messenger(channel="whatsapp", config=config, client_name="session_sweeper")
                        messenger.just_reply(reply, session.contact.phone)
                except Exception as e:
                    logger.exception(f"Sweep failed for session {session.pk}: {e}")


@shared_task(bind=True, task_kwargs={'queue': settings.HIGH_PRIORITY_Q}, retry_kwargs={'max_retries': 5, 'countdown': 10}, retry_backoff=True)
def whatsapp_webhook_handler(self, body: dict):
    task_id = current_task.request.id
    q_name = self.request.delivery_info['routing_key']

    logger.info(f'Processing whatsapp webhook ingress ---> {task_id} from {q_name}')

    try:
        portal_config = PlatformConfiguration.objects.first()
    except PlatformConfiguration.DoesNotExist:
        raise ImproperlyConfigured("No Portal config present")

    print(body)
    received_webhook = WhatsappWebhook(body)
    webhook_type = received_webhook.get_type()
    logger.info(f'Tipo de webhook recibido: %s', webhook_type)

    if webhook_type != "messages":
        print(f'Received webhook type {webhook_type}')
        received_webhook.display_content()
        redirect_webhook(url=portal_config.whatsapp_webhook_redirect, body=body)
        return {"status": "forwarded", "reason": f"unsupported_type_{webhook_type}"}

    try:
        received_whatsapp = WhatsappMessage(body)
    except Exception:
        logger.exception("Error parsing WhatsApp webhook payload")
        redirect_webhook(url=portal_config.whatsapp_webhook_redirect, body=body)
        return {"status": "forwarded", "reason": "parse_error"}

    logger.info(
        "Resolved inbound asset candidate for WABA:%s--%s msg_id:%s",
        received_whatsapp.get_waba_id(),
        received_whatsapp.get_waba_phone_id(),
        received_whatsapp.msg_id,
    )

    try:
        owner_config = get_whatsapp_integration_by_asset_ids(
            received_whatsapp.get_waba_id(),
            received_whatsapp.get_waba_phone_id(),
        )
    except ValueError:
        logger.exception(
            "Ambiguous WhatsApp asset ownership for waba_id=%s phone_id=%s",
            received_whatsapp.get_waba_id(),
            received_whatsapp.get_waba_phone_id(),
        )
        redirect_webhook(url=portal_config.whatsapp_webhook_redirect, body=body)
        return {"status": "forwarded", "reason": "owner_ambiguous"}

    if owner_config is None:
        logger.warning(
            "No tenant owns WhatsApp asset waba_id=%s phone_id=%s; forwarding webhook",
            received_whatsapp.get_waba_id(),
            received_whatsapp.get_waba_phone_id(),
        )
        redirect_webhook(url=portal_config.whatsapp_webhook_redirect, body=body)
        return {"status": "forwarded", "reason": "owner_not_found"}

    tenant_task = process_whatsapp_webhook_for_tenant.apply_async(
        kwargs={
            "body": body,
            "tenant_id": owner_config.tenant_id,
            "instance_id": owner_config.instance_id,
        },
        queue=settings.HIGH_PRIORITY_Q,
    )
    logger.info(
        "Transferred WhatsApp webhook to tenant task %s for tenant=%s instance=%s",
        tenant_task.id,
        owner_config.tenant_id,
        owner_config.instance_id,
    )
    return {
        "status": "queued",
        "task_id": tenant_task.id,
        "tenant_id": owner_config.tenant_id,
        "instance_id": owner_config.instance_id,
    }


@shared_task(bind=True, queue=settings.HIGH_PRIORITY_Q, max_retries=5, default_retry_delay=10, autoretry_for=(Exception,), retry_backoff=True, retry_backoff_max=300)
def process_whatsapp_webhook_for_tenant(self, body: dict, tenant_id: int, instance_id: str = "default"):
    task_id = current_task.request.id
    q_name = self.request.delivery_info['routing_key']
    start_time = timezone.now()

    logger.info(
        "Processing whatsapp webhook for tenant %s instance %s ---> %s from %s",
        tenant_id,
        instance_id,
        task_id,
        q_name,
    )

    tenant = Tenant.objects.filter(pk=tenant_id).first()
    if tenant is None:
        logger.warning(
            "Tenant %s no longer exists for WhatsApp webhook instance=%s; forwarding webhook",
            tenant_id,
            instance_id,
        )
        redirect_webhook(url=PlatformConfiguration.objects.first().whatsapp_webhook_redirect, body=body)
        return {"status": "forwarded", "reason": "tenant_not_found", "tenant_id": tenant_id}

    tenant_token = current_tenant.set(tenant)
    try:
        with tenant_rls_context(getattr(tenant, "schema_name", None)):
            try:
                portal_config = PlatformConfiguration.objects.first()
            except PlatformConfiguration.DoesNotExist:
                raise ImproperlyConfigured("No Portal config present")

            print(body)
            received_webhook = WhatsappWebhook(body)
            webhook_type = received_webhook.get_type()
            logger.info(f'Tipo de webhook recibido: %s', webhook_type)

            payload_kwargs = {
                "wa_body": json.dumps(body),
                "status": webhook_type,
                "tenant_id": tenant.pk,
            }

            received_whatsapp = None
            if webhook_type == "messages":
                try:
                    received_whatsapp = WhatsappMessage(body)
                except Exception:
                    logger.exception("Error parsing WhatsApp webhook payload")
                    payload_kwargs["status"] = "parse_error"
                else:
                    if received_whatsapp.timestamp:
                        payload_kwargs["timestamp"] = str(received_whatsapp.timestamp)

                    if received_whatsapp.is_status() and received_whatsapp.status:
                        payload_kwargs["status"] = received_whatsapp.status
                    elif received_whatsapp.msg_type:
                        payload_kwargs["status"] = received_whatsapp.msg_type

            WaPayloads.objects.create(**payload_kwargs)

            if webhook_type != "messages":
                print(f'Received webhook type {webhook_type}')
                received_webhook.display_content()
                redirect_webhook(url=portal_config.whatsapp_webhook_redirect, body=body)
                return {"status": "forwarded", "reason": f"unsupported_type_{webhook_type}"}

            if received_whatsapp is None:
                redirect_webhook(url=portal_config.whatsapp_webhook_redirect, body=body)
                return {"status": "forwarded", "reason": "parse_error"}

            integration_config = IntegrationConfig.get_for_tenant(tenant, "whatsapp", instance_id)
            if integration_config is None or not integration_config.enabled:
                logger.warning(
                    "No enabled WhatsApp config found for tenant=%s instance=%s; forwarding webhook",
                    tenant.pk,
                    instance_id,
                )
                redirect_webhook(url=portal_config.whatsapp_webhook_redirect, body=body)
                return {
                    "status": "forwarded",
                    "reason": "owner_not_found",
                    "tenant_id": tenant.pk,
                    "instance_id": instance_id,
                }

            config = get_tenant_config_for_integration_instance(tenant, "whatsapp", instance_id)

            logger.info(
                "Payload for WABA:%s--%s msg_id:%s",
                received_whatsapp.get_waba_id(),
                received_whatsapp.get_waba_phone_id(),
                received_whatsapp.msg_id,
            )

            if received_whatsapp.is_message():
                phone = received_whatsapp.get_contact_number()
                if is_blacklisted_contact(phone, config.tenant):
                    logger.info("Ignoring message from blacklisted contact %s", phone)
                    try:
                        WhatsappBusinessClient(config).mark_as_read(received_whatsapp.msg_id)
                    except Exception:
                        logger.exception("Failed to mark blacklisted message as read")
                    return {"status": "ignored", "reason": "blacklisted_contact"}

            # TODO: match assistant with the incomming channel so we can have more than 1 channel.
            if config.conversation_handler == 'chatbot':
                process_message_with_chatbot(received_whatsapp=received_whatsapp, config=config)
            elif config.conversation_handler == 'assistant' and config.assistants_enabled:
                logger.info(check_elapsed_time(start_time, "Inicio a Procesar con Asistente"))
                process_message_with_assistant(received_whatsapp=received_whatsapp, config=config)
            elif config.conversation_handler == 'agent':
                logger.info(check_elapsed_time(start_time, "Inicio a Procesar con Agente"))
                process_message_with_agent(received_whatsapp=received_whatsapp, config=config)
            else:
                redirect_webhook(url=portal_config.whatsapp_webhook_redirect, body=body)
                return {"status": "forwarded", "reason": "no_handler"}

            return {"status": "processed", "tenant_id": tenant.pk, "instance_id": instance_id}
    finally:
        current_tenant.reset(tenant_token)


@shared_task(bind=True, task_kwargs={'queue': settings.HIGH_PRIORITY_Q}, retry_kwargs={'max_retries': 5, 'countdown': 10}, retry_backoff=True)
def instagram_webhook_handler(self, body: dict):
    print(body)
    text = None

    if body.get("object") == "instagram":
        print("Procesando mensaje recibido de instagram")
        entry = body.get("entry")[0]
        entry_id = entry.get("entry_id")
        entry_messaging = entry.get("messaging")[0]
        sender_id = entry_messaging.get("sender").get("id")
        recipient_id = entry_messaging.get("recipient").get("id")

        if entry_messaging.get("message"):
            message_id = entry_messaging.get("message").get("mid")

        message = entry_messaging.get("message")
        if message:
            text = message.get("text")
            if text:
                print(text)

            attachments = message.get("attachments")
            if attachments:
                for a in attachments:
                    print(a.get("type"))
                    print(a.get("payload"))

        token = 'IGAATDpbObXZBRBZAE1LaHNzUHVIaWdBR2xVOEtrQTYyMUhoc19oTUlUakhuUnczUjY4VWltLTZA2RGxVUzJPdVNDbm5laks2d0xtUnBIS0VrY1h1T1k1MlhqaUZAKVXI1VndlbUZAFNXFMMjY2dHh0ZAWJ1dWgxdzRJcGRkM3BtZAjE2MAZDZD'
        id_moio_digital = '17841416118331552'
        # ig_app = '1341016357167076'
        # ig_secret = '1f20795b78f39073df58980c4aefd18a'

        if text:
            print(f"Contestando eco: {text}")
            url = f"https://graph.instagram.com/v22.0/{id_moio_digital}/messages"
            headers = {
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json"
            }

            data = {
                "recipient": {
                    "id": sender_id
                    },
                "message": {
                    "text": text
                    }
            }
            resultados = requests.post(url, headers=headers, json=data)
            print(resultados.json())


@shared_task(bind=True, task_kwargs={'queue': settings.HIGH_PRIORITY_Q}, retry_kwargs={'max_retries': 5, 'countdown': 10}, retry_backoff=True)
def messenger_webhook_handler(self, body: dict):
    print(body)


@shared_task(bind=True, queue=settings.MEDIUM_PRIORITY_Q)
def handle_received_email(self, data, tenant_code):
    task_id = current_task.request.id
    q_name = self.request.delivery_info['routing_key']

    logger.info(f'Processing task ---> {task_id} from {q_name}')


@shared_task(bind=True, queue=settings.MEDIUM_PRIORITY_Q)
def handle_received_order(self, data, tenant_code):
    task_id = current_task.request.id
    q_name = self.request.delivery_info['routing_key']
    logger.info(f'Processing task ---> {task_id} from {q_name}')


@shared_task(bind=True, queue=settings.LOW_PRIORITY_Q)
def sync_email_account_task(self, account_id):
    task_id = current_task.request.id
    q_name = self.request.delivery_info['routing_key']
    logger.info(f'Processing task ---> {task_id} from {q_name}')

    try:
        account = EmailAccount.objects.get(id=account_id)
        sync_email_account(account)
    except EmailAccount.DoesNotExist:
        # Optionally log the missing account
        pass


@shared_task(bind=True, queue=settings.LOW_PRIORITY_Q)
def sync_all_email_accounts(self):
    task_id = current_task.request.id
    q_name = self.request.delivery_info['routing_key']
    logger.info(f'Processing task ---> {task_id} from {q_name}')

    accounts = EmailAccount.objects.all()
    tasks = group(sync_email_account_task.s(account.id) for account in accounts)
    tasks.apply_async()


def process_email_with_assistant(received_email: EmailMessage, config):

    logger.info("Processing %s",config.whatsapp_name)

    sender = received_email.sender.split("<")
    sender_name = sender[0]
    sender_email = sender[1]

    # received_email.message_id
    # Crear el usuario a partir de los datos del mensaje recibido
    contact = Contact.create_or_update(
        email=sender_email,
        fullname=sender_name,
        tenant=config.tenant,
        source="email"
    )

    assistant = MoioAssistant(
        openai_key=config.openai_api_key,
        contact=contact,
        tenant_id=config.tenant_id,
        default_assistant_id=config.assistants_default_id,
        channel="email"
    )

    email_data = {
        "subject": received_email.subject,
        "body": received_email.body,
        "received": received_email.date_received
    }

    message_content = json.dumps(email_data)

    reply = assistant.reply_to_this(message_content=message_content)

    received_email.is_read = True
    received_email.save()

    # Send the Reply to the Contact
    moio_messenger = Messenger(channel=assistant.channel, config=config, client_name="assistant_email")

    moio_messenger.reply_email(reply, sender_email)


@shared_task(bind=True, queue=settings.MEDIUM_PRIORITY_Q)
def archive_conversation(self, session_id):
    task_id = current_task.request.id
    q_name = self.request.delivery_info['routing_key']
    logger.info(f'Processing chatbot heartbeat ---> {task_id} from {q_name}')

    print(f"Ending Conversation {session_id}")

    session = AgentSession.objects.get(pk=session_id)
    config = get_tenant_config(session.tenant)

    agent = MoioAgent(config=config, contact=session.contact)
    reply = agent.internal_command(message="end_conversation")

    moio_messenger = Messenger(channel=session.channel, config=config, client_name="session-archive")

    if type(reply) is not str:
        reply = reply.model_dump()

    moio_messenger.structured_reply(reply, session.contact.phone)


@shared_task(
    bind=True,
    queue=settings.HIGH_PRIORITY_Q,
    max_retries=5,
    default_retry_delay=10,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=300,
)
def sync_tenant_tools_task(self):
    """
    Sync all available tools to every tenant's TenantToolConfiguration.
    
    Uses exponential backoff with max 5 retries.
    Runs on HIGH_PRIORITY_Q for fast startup.
    """
    try:
        from chatbot.models.sync_tools import sync_tenant_tools
        sync_tenant_tools()
        logger.info("Successfully synced tenant tool configurations")
    except Exception as e:
        logger.error(f"Error syncing tenant tools (attempt {self.request.retries + 1}/5): {e}")
        raise


@shared_task(
    bind=True,
    queue=settings.HIGH_PRIORITY_Q,
    max_retries=3,
    default_retry_delay=5,
    autoretry_for=(Exception,),
    retry_backoff=True,
)
def sync_single_tenant_tools_task(self, tenant_id: int):
    """
    Sync all available tools for a specific tenant.

    Called when a new tenant is created.
    """
    try:
        from chatbot.services.sync_tools import sync_tenant_tools

        sync_tenant_tools(tenant_ids=[tenant_id])
        logger.info("Successfully synced tools for tenant %s", tenant_id)
    except Exception as e:
        logger.error("Error syncing tools for tenant %s: %s", tenant_id, e)
        raise
