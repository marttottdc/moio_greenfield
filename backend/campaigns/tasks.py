import json

import pandas as pd
from celery import shared_task
from django.conf import settings
from django.core.serializers.json import DjangoJSONEncoder
from django.db.models import F
from django.utils import timezone
from django.utils.translation import gettext as _

from campaigns.core.campaigns_engine import whatsapp_message_validator, whatsapp_message_generator, sanitize_key, contact_validator
from campaigns.models import CampaignData, CampaignDataStatus, Campaign, CampaignDataStaging, Status
from chatbot.core.moio_agent import AgentEngine
from chatbot.lib.whatsapp_client_api import WhatsappBusinessClient, template_requirements
from django.db.utils import OperationalError
from django.db import close_old_connections

import logging

from crm.services.contact_service import ContactService
from moio_platform.core.events import emit_event


logger = logging.getLogger(__name__)


from itertools import islice
from django.db import transaction
from django.conf import settings


def _chunked(iterable, size):
    it = iter(iterable)
    while True:
        batch = list(islice(it, size))
        if not batch:
            break
        yield batch


@shared_task(bind=True, queue=settings.MEDIUM_PRIORITY_Q)
def execute_campaign(self, campaign_pk: str):
    try:
        campaign = Campaign.objects.get(pk=campaign_pk)
    except Campaign.DoesNotExist:
        return []

    tenant = campaign.tenant
    cfg = campaign.config or {}
    data_config = cfg.get("data") or {}
    schedule_config = cfg.get("schedule") or {}
    defaults_config = cfg.get("defaults") or {}

    data_staging_pk = data_config.get("data_staging")
    if not data_staging_pk:
        return []

    try:
        data_staging = CampaignDataStaging.objects.get(pk=data_staging_pk, tenant=tenant)
    except CampaignDataStaging.DoesNotExist:
        return []

    mapped_data = data_staging.mapped_data or []
    if not mapped_data:
        return []

    batch_size = int(schedule_config.get("batch_size", 100))

    job_ids = []

    for msg_batch in _chunked(mapped_data, batch_size):

        objs = [
            CampaignData(
                tenant=tenant,
                campaign=campaign,
                variables=msg,
            )
            for msg in msg_batch
        ]

        with transaction.atomic():
            created = CampaignData.objects.bulk_create(
                objs,
                batch_size=min(len(objs), 100),
            )

        cdo_ids = [str(o.pk) for o in created]

        job = send_outgoing_messages_batch.apply_async(
            args=[cdo_ids, str(campaign_pk)],
            queue=settings.MEDIUM_PRIORITY_Q
        )

        job_ids.append(job.id)   # <-- keep only IDs (string, serializable)

    campaign.status = Status.ACTIVE
    campaign.save()

    try:
        audience = getattr(campaign, "audience", None)
        emit_event(
            name="campaign.started",
            tenant_id=campaign.tenant.tenant_code,
            actor={"type": "system", "id": "campaigns.tasks.execute_campaign"},
            entity={"type": "campaign", "id": str(campaign.pk)},
            payload={
                "campaign_id": str(campaign.pk),
                "name": campaign.name,
                "channel": campaign.channel,
                "kind": campaign.kind,
                "status": campaign.status,
                "audience_id": str(audience.pk) if audience else None,
                "audience_name": audience.name if audience else None,
                "audience_size": getattr(audience, "size", None) if audience else None,
                "job_ids": job_ids,
                "started_at": timezone.now().isoformat(),
            },
            source="task",
        )
    except Exception:
        # Don't fail campaign execution due to event emission issues.
        pass

    return job_ids    # <-- fully JSON serializable


@shared_task(bind=True, queue=settings.MEDIUM_PRIORITY_Q)
def validate_campaign(self, campaign_pk: str):
    try:
        campaign = Campaign.objects.get(pk=campaign_pk)
    except Campaign.DoesNotExist:
        return None

    tenant = campaign.tenant

    print(f"Processing campaign {campaign.name}")

    data_config = campaign.config.get("data", None)
    message_config = campaign.config.get("message", None)
    schedule_config = campaign.config.get("schedule", None)
    default_config = campaign.config.get("defaults", None)

    print(f"Data config: {data_config}")
    print(f"Message config: {message_config}")
    print(f"Schedule config: {schedule_config}")

    whatsapp_template_id = message_config.get("whatsapp_template_id", None)

    if whatsapp_template_id:

        print(f"Whatsapp template id: {whatsapp_template_id} confirmed")
        wa = WhatsappBusinessClient(tenant.configuration.first())
        template = wa.template_details(whatsapp_template_id)
        requirements = template_requirements(template)
        namespace = wa.retrieve_template_namespace()

    else:
        return None

    data_staging_pk = data_config.get("data_staging", None)

    message_mapping = message_config.get("map", None)

    if message_mapping:
        print(f"Message mapping: {message_mapping} confirmed")

    if data_staging_pk:

        try:
            data_staging = CampaignDataStaging.objects.get(pk=data_staging_pk)
            print(f"Data staging: {data_staging} confirmed")

            if data_staging.mapped_data is None or len(data_staging.mapped_data) == 0:

                logger.info(f"Starting data map")
                df = pd.DataFrame(data_staging.raw_data)

                message_list = []
                errors = 0
                for idx, row in df.iterrows():

                    message_values = {}
                    message = {
                        "message_type": "whatsapp",
                        "template_id": whatsapp_template_id,
                        "valid": False,
                        "values": message_values
                    }
                    for mapping_item in message_mapping:

                        template_element = sanitize_key(mapping_item.get("template_var", None))
                        target_col = mapping_item.get("target_field", None)

                        if mapping_item.get("type", None) == 'variable':

                            if mapping_item.get("template_element", None) == 'header':

                                if mapping_item.get("template_var", None) == 'image':
                                    message_values["image_link"] = row[target_col]

                                elif mapping_item.get("template_var", None) == 'document':
                                    message_values["document_link"] = row[target_col]

                            else:
                                message_values[template_element] = row[target_col]
                        else:
                            if mapping_item.get("template_element", None) == 'header':

                                if mapping_item.get("template_var", None) == 'image':
                                    message_values["image_link"] = target_col

                                elif mapping_item.get("template_var", None) == 'document':
                                    message_values["document_link"] = target_col
                            else:
                                message_values[template_element] = target_col

                    default_country_code = default_config.get("country_code", None)

                    #  if default_config.get("auto_correct", False) is True:

                    message = whatsapp_message_validator(tenant, message, default_country_code)

                    contact = contact_validator(tenant, message)

                    print(f"Message validator: {message}")

                    if message.get("valid", False):
                        print("Valid message")

                        whatsapp_message = whatsapp_message_generator(tenant=tenant,
                                                                      message_data=message["values"],
                                                                      requirements=requirements,
                                                                      namespace=namespace,
                                                                      template=template)

                        message_object = {
                            "contact": contact,
                            "message": whatsapp_message,
                        }

                        message_list.append(message_object)

                    else:
                        errors += 1

                # print(message_list)
                data_staging.errors = errors
                data_staging.mapped_data = message_list
                for m in message_list:
                    logger.info(m)

                data_staging.save()

            return data_staging.mapped_data

        except CampaignDataStaging.DoesNotExist:
            print("Data staging does not exist")


@shared_task(
    bind=True,
    queue=settings.MEDIUM_PRIORITY_Q,
    rate_limit="20/m",                 # <= throttle starts here
    autoretry_for=(OperationalError,), # retry on transient DB errors
    retry_backoff=True,
    retry_jitter=True,
    max_retries=5,
)
def send_outgoing_messages(self, msg, campaign_pk):
    close_old_connections()
    contact_data = msg.get("contact", None)
    whatsapp_message = msg.get("message", None)

    try:
        campaign = Campaign.objects.get(pk=campaign_pk)

    except Campaign.DoesNotExist:
        return None

    tenant = campaign.tenant
    config = tenant.configuration.first()

    wa = WhatsappBusinessClient(config)
    print("sending message")
    print(msg)

    configuration_defaults = campaign.config.get("defaults", None)
    if configuration_defaults.get("save_contacts"):

        fullname = contact_data.get("fullname", "")
        phone = contact_data.get("phone", "")
        ctype_pk = configuration_defaults.get("contact_type", None)

        print("Creating Contact")
        new_contact = ContactService.contact_upsert(
            tenant=campaign.tenant,
            fullname=fullname,
            phone=phone,
            ctype_pk=ctype_pk)

        print(f"Contacts created {new_contact}")

        if configuration_defaults.get("notify_agent"):

            agent = AgentEngine(config, new_contact, started_by=f"campaign {campaign.name}")
            command = f"""
                        This message belongs to an outgoing campaign sent by {tenant.nombre}
                        agent must be aware and ready to continue the conversation seamlessly. 
                        campaign: {campaign.description} 
                        msg: {whatsapp_message}
            """
            agent.register_outgoing_campaign_message(command)

            # tranlated_msg = translate_msg(msg)

        send_result = wa.send_message(whatsapp_message, campaign.name)
        message_sent = isinstance(send_result, dict) and send_result.get("success", False)
        if message_sent:
            pass
            # session.add_message(tranlated_msg)

    print("Logging message result")
    close_old_connections()


def is_message_success(result):
    """Returns True only if WhatsApp confirmed the message was accepted/sent."""

    if not isinstance(result, dict):
        return False

    # Explicit error field → failed
    if result.get("error"):
        return False

    # WhatsApp Cloud API / BSP success structure
    try:
        status = result["messages"][0]["message_status"]
        return status in ("accepted", "sent", "delivered")
    except Exception:
        return False


def normalize_message_result(message_result):
    return {
        "status": message_result.get("status"),
        "id": message_result.get("id"),
        "error": message_result.get("error"),
    }


def safe_json(data):
    try:
        return json.loads(json.dumps(data, cls=DjangoJSONEncoder))
    except Exception:
        return str(data)  # Last fallback


@shared_task(
    bind=True,
    queue=settings.MEDIUM_PRIORITY_Q,
    autoretry_for=(OperationalError,),
    retry_backoff=True,
    max_retries=5,
)
def send_outgoing_messages_batch(self, batch: list, campaign_pk):

    close_old_connections()

    # Return structure
    summary = {
        "campaign_id": campaign_pk,
        "processed": 0,
        "sent": 0,
        "failed": 0,
        "skipped": 0,
        "items": []
    }

    try:
        campaign = Campaign.objects.get(pk=campaign_pk)
        summary["campaign"] = campaign.name

    except Campaign.DoesNotExist:
        return summary

    tenant = campaign.tenant
    config = tenant.configuration.first()

    wa = WhatsappBusinessClient(config)
    defaults = campaign.config.get("defaults", {})

    # ---------------------------------------------------------
    # PROCESS EACH ITEM
    # ---------------------------------------------------------
    for item in batch:

        summary["processed"] += 1

        try:
            with transaction.atomic():

                # ---------------------------------------------------------
                # LOCK the row. If locked → skip (another worker has it)
                # ---------------------------------------------------------
                try:
                    cdo = (
                        CampaignData.objects
                        .select_for_update(skip_locked=True)
                        .get(pk=item, status=CampaignDataStatus.PENDING)
                    )
                except CampaignData.DoesNotExist:
                    summary["skipped"] += 1
                    summary["items"].append({
                        "id": item,
                        "status": "skipped",
                        "result": "Already processed or locked"
                    })
                    continue

                msg_vars = cdo.variables
                contact_data = msg_vars.get("contact", {})
                whatsapp_message = msg_vars.get("message", {})

                fullname = contact_data.get("fullname", "")
                phone = contact_data.get("phone", "")
                ctype_pk = defaults.get("contact_type")

                # ---------------------------------------------------------
                # UPSERT CONTACT (may raise)
                # ---------------------------------------------------------
                try:
                    new_contact = ContactService.contact_upsert(
                        tenant=tenant,
                        fullname=fullname,
                        phone=phone,
                        ctype_pk=ctype_pk
                    )
                except Exception as e:
                    cdo.status = CampaignDataStatus.SKIPPED
                    cdo.result = {"error": str(e)}
                    cdo.save()

                    summary["skipped"] += 1
                    summary["items"].append({
                        "id": item,
                        "status": "skipped",
                        "result": str(e)
                    })
                    continue

                # ---------------------------------------------------------
                # SEND MESSAGE
                # ---------------------------------------------------------
                message_sent, message_result = wa.send_outgoing_template(
                    whatsapp_message,
                    campaign.name
                )

                successful = is_message_success(message_result)

                # ---------------------------------------------------------
                # SUCCESS
                # ---------------------------------------------------------
                if successful:
                    cdo.status = CampaignDataStatus.SENT
                    cdo.sent_at = timezone.now()
                    cdo.result = message_result
                    cdo.save()

                    # atomic increment
                    Campaign.objects.filter(pk=campaign.pk).update(sent=F('sent') + 1)

                    summary["sent"] += 1
                    summary["items"].append({
                        "id": item,
                        "status": "sent",
                        "result": str(message_result)
                    })

                    # Notify agent (optional)
                    if defaults.get("notify_agent"):
                        agent = AgentEngine(config, new_contact, started_by=f"campaign {campaign.name}")
                        agent.register_outgoing_campaign_message(
                            f"""Outgoing campaign message sent by {tenant.nombre}.
                                Campaign: {campaign.description}.
                                Payload: {whatsapp_message}"""
                        )

                # ---------------------------------------------------------
                # FAILURE
                # ---------------------------------------------------------
                else:
                    cdo.status = CampaignDataStatus.FAILED
                    cdo.result = message_result
                    cdo.save()

                    summary["failed"] += 1
                    summary["items"].append({
                        "id": item,
                        "status": "failed",
                        "result": str(message_result)
                    })

        except Exception as e:
            logger.error(f"Unexpected error processing item {item}: {e}")

            summary["failed"] += 1
            summary["items"].append({
                "id": item,
                "status": "failed",
                "result": str(e)
            })

        finally:
            close_old_connections()

    return summary