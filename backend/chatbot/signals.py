import os
import logging

from django.conf import settings
from django.db import transaction
from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync
from django.utils import timezone

from chatbot.models.chatbot_session import ChatbotMemory, ChatbotSession
from crm.serializers import ContactSerializer
from central_hub.tenant_config import get_tenant_config
from tenancy.tenant_support import tenant_schema_context
from moio_platform.lib.email import send_email
from cacheops.signals import cache_read
from websockets_app.services.publisher import WebSocketEventPublisher
from chatbot import events as chatbot_events

logger = logging.getLogger(__name__)


@receiver(pre_save, sender=ChatbotSession)
def chatbot_session_capture_previous(sender, instance, **kwargs):
    """Attach previous DB state so post_save can detect transitions."""
    if not instance.pk:
        instance._previous = None
        return
    try:
        instance._previous = sender.objects.filter(pk=instance.pk).first()
    except Exception:
        instance._previous = None


@receiver(post_save, sender=ChatbotSession)
def session_ended(sender, instance, created, **kwargs):
    old = getattr(instance, "_previous", None)

    if created:
        try:
            chatbot_events.session_started(instance)
        except Exception:
            pass
        return

    # Triggers only on status change from active to not active
    if old and old.active != instance.active and instance.active == False:
        try:
            chatbot_events.session_ended(instance)
        except Exception:
            pass

        if instance.contact:

            contact = instance.contact

            if instance.started_by == "user":
                subject = f"Informe de Conversacion iniciada por el usuario : {contact.fullname}"
            else:
                subject = f"Informe de Conversacion: {instance.started_by}"

            name = f"{contact.fullname}"
            whatsapp_name = f"{contact.whatsapp_name}"
            email = f"{contact.email}"
            phone = f"{contact.phone}"

        else:
            subject = f"Informe de Conversacion: {instance.pk}"
            name = "desconocido"
            email = "desconocido"
            phone = "desconocido"
            whatsapp_name = "desconocido"

        last_interaction_local_time = timezone.localtime(instance.last_interaction)

        message = f"""
            <html>
                <body>
                    <h2>{instance.tenant.nombre} Informe de Chatbot </h2>
                    <p><strong>Nombre:</strong>{name} </p>
                    <p><strong>Nombre en Whatsapp:</strong>{whatsapp_name} </p>
                    <p><strong>Teléfono:</strong>{phone}</p>
                    <p><strong>Email:</strong>{email}</p>
                    <p><strong>Canal:</strong> {instance.channel} </p>
                    <p><strong>Resumen:</strong> {instance.final_summary} </p>
                    <p><strong>Ultima Interacción:</strong> {last_interaction_local_time.strftime('%Y-%m-%d %H:%M:%S %Z')} </p>
                    <hr>
                    <p> <strong>ID de Conversacion:</strong>{instance.pk}</p>
                </body>
            </html>
            """

        schema_name = getattr(instance.tenant, "schema_name", None)
        with tenant_schema_context(schema_name):
            config = get_tenant_config(instance.tenant)

        recipient_list = config.default_notification_list.split(",")
        tenant_id = config.tenant_id

        logger.info(f'Enviando email para {config.tenant}')

        # Enqueue in the custom "email_queue"
        transaction.on_commit(lambda: send_email.apply_async(
            args=[message, subject, recipient_list, tenant_id],
            queue=settings.MEDIUM_PRIORITY_Q
        ))


@receiver(cache_read)
def log_cache_access(sender, func, hit, **kwargs):
    logger.debug(f"Cache {'hit' if hit else 'miss'} for {sender}")


# Import Tenant for signal registration
from central_hub.models import Tenant


@receiver(post_save, sender=Tenant)
def sync_tools_for_new_tenant(sender, instance, created, **kwargs):
    """Sync tool configurations when a new tenant is created."""
    if created:
        try:
            from chatbot.tasks import sync_single_tenant_tools_task
            
            # Delay slightly to ensure tenant is committed
            transaction.on_commit(lambda: sync_single_tenant_tools_task.apply_async(
                args=[instance.id],
                countdown=2,
                queue=settings.HIGH_PRIORITY_Q
            ))
            logger.info(f"Scheduled tool sync for new tenant {instance.id}")
        except Exception as e:
            logger.warning(f"Could not schedule tool sync for tenant {instance.id}: {e}")