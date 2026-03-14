# audiences/services.py
from __future__ import annotations

from celery import shared_task
from django.conf import settings
from django.core.exceptions import ValidationError

from crm.models import Contact
from campaigns.models import Audience, AudienceKind, AudienceMembership
import csv
from django.db import transaction
from django.db.models import Q, Case, When, Max, DateTimeField
from dateutil.parser import isoparse
from campaigns.models import Campaign, CampaignData, CampaignDataStatus, Status
from django.db import transaction


import uuid
from typing import Iterable, Sequence, Union, Optional, Tuple, Dict, Any, List
from datetime import datetime

from django.db import transaction, models
from django.utils import timezone
from django.core.exceptions import ValidationError

from campaigns.models import Audience, AudienceMembership, CampaignData
from crm.models import Contact
from moio_platform.lib.tools import remove_keys
from campaigns.tasks import execute_campaign, validate_campaign
from chatbot.lib.whatsapp_client_api import WhatsappBusinessClient, template_requirements
from central_hub.tenant_config import get_tenant_config
from chatbot.models.wa_message_log import WaMessageLog


def _normalize_rows(rows):
    """
    Accepts either:
      - {"field": "...", "op": "...", "value": ..., "value_to": ..., "negate": bool}
      - legacy single-key dicts like {"city": "NY"}
    Returns a list of dicts suitable for ConditionForm initial.
    """
    norm = []
    for r in rows or []:
        if not isinstance(r, dict):
            continue
        if "field" in r:                 # already full shape
            norm.append(r)
            continue
        if len(r) == 1:                  # legacy {"field": value}
            k, v = next(iter(r.items()))
            norm.append({"field": k, "op": "eq", "value": v})
    return norm


def render_variables(template, member):
    """
    Return a dict of variables required by `template`
    using AudienceMember snapshot data. Extend this as needed.
    """
    # Dummy example – pull from JSONField 'extra' or fallback to name/email
    vars = {
        "first_name":  member.name.split()[0] if member.name else "",
        "email":       member.email,
        "phone":       member.phone,
        **(member.extra or {}),
    }
    missing = [k for k in template.required_vars if k not in vars]
    if missing:
        return None, missing
    return vars, None


def build_campaign_data(campaign, template):
    """
    Materialise a CampaignData row for every AudienceMember of the campaign.
    Skips members missing required vars.
    """
    rows, skipped = [], 0
    for m in campaign.audience.members.select_related("audience"):
        payload, missing = render_variables(template, m)
        if missing:
            skipped += 1
            continue

        rows.append(
            CampaignData(
                tenant=campaign.tenant,
                campaign=campaign,
                recipient=m,
                variables=payload,
                scheduled_at=campaign.config.get("send_window_start")  # optional
            )
        )

    with transaction.atomic():
        CampaignData.objects.bulk_create(rows, ignore_conflicts=True)
    return len(rows), skipped


def ensure_static(audience: Audience):
    if audience.kind != AudienceKind.STATIC:
        raise ValidationError("Manual membership edits are only allowed for STATIC audiences.")


@shared_task(queue=settings.LOW_PRIORITY_Q)
def rebuild_dynamic_audience(audience_id):
    """Celery task to rebuild a dynamic audience"""
    aud = Audience.objects.get(pk=audience_id, kind=AudienceKind.DYNAMIC)

    # 1) Compute desired set from rules
    desired_ids = set(evaluate_rules(aud.rules).values_list("id", flat=True))

    # 2) Current set
    current_ids = set(
        AudienceMembership.objects.filter(audience=aud)
        .values_list("contact_id", flat=True)
    )

    to_add = desired_ids - current_ids
    to_del = current_ids - desired_ids

    # 3) Apply changes
    AudienceMembership.objects.bulk_create(
        [AudienceMembership(audience=aud, contact_id=i, tenant=aud.tenant) for i in to_add],
        ignore_conflicts=True,
    )
    if to_del:
        AudienceMembership.objects.filter(audience=aud, contact_id__in=list(to_del)).delete()

    # 4) Update cached metrics
    size = AudienceMembership.objects.filter(audience=aud).count()
    Audience.objects.filter(pk=audience_id).update(
        size=size, materialized_at=timezone.now()
    )


# ---------------------------
# Helpers
# ---------------------------

def _get_audience_for_update(audience: Union[Audience, uuid.UUID, str]) -> Audience:
    """Get audience instance with select_for_update lock"""
    if isinstance(audience, Audience):
        return audience
    return Audience.objects.select_for_update().get(pk=audience)


def _coerce_contact_ids(contacts: Union[Iterable[Contact], Iterable[uuid.UUID], Iterable[int], models.QuerySet]) -> Sequence:
    """
    Accepts Contact queryset / list of Contact instances / list of IDs.
    Returns a list of primary keys.
    """
    if hasattr(contacts, "values_list"):
        return list(contacts.values_list("id", flat=True))
    # Contacts or raw IDs
    ids = []
    for c in contacts:
        ids.append(c.id if isinstance(c, Contact) else c)
    return ids


def _enforce_static(aud: Audience) -> None:
    if aud.kind != AudienceKind.STATIC:
        raise ValidationError("Manual membership edits are only allowed for STATIC audiences.")


CHUNK_SIZE = 1000
# ---------------------------
# Public API
# ---------------------------


@transaction.atomic
def add_static_contacts(audience: Union[Audience, uuid.UUID, str],
                        contacts: Union[Iterable[Contact], Iterable[uuid.UUID], models.QuerySet]) -> Tuple[int, int]:
    """
    Upsert memberships for a STATIC audience.
    Returns (created_count, total_now).
    """
    aud = _get_audience_for_update(audience)
    _enforce_static(aud)
    ids = _coerce_contact_ids(contacts)
    if not ids:
        return 0, aud.size

    # Bulk upsert (ignore_conflicts to avoid UNIQUE(audience, contact) errors)
    payload = (AudienceMembership(audience=aud, contact_id=i) for i in ids)
    created = AudienceMembership.objects.bulk_create(payload, ignore_conflicts=True, batch_size=CHUNK_SIZE)
    # Refresh cached size
    total = AudienceMembership.objects.filter(audience=aud).count()
    Audience.objects.filter(pk=aud.pk).update(size=total, materialized_at=timezone.now())
    return len(created), total


@transaction.atomic
def remove_static_contacts(audience: Union[Audience, uuid.UUID, str],
                           contacts: Union[Iterable[Contact], Iterable[uuid.UUID], models.QuerySet]) -> Tuple[int, int]:
    """
    Remove memberships for a STATIC audience.
    Returns (deleted_count, total_now).
    """
    aud = _get_audience_for_update(audience)
    _enforce_static(aud)
    ids = _coerce_contact_ids(contacts)
    if not ids:
        return 0, aud.size

    qs = AudienceMembership.objects.filter(audience=aud, contact_id__in=ids)
    deleted, _ = qs.delete()
    total = AudienceMembership.objects.filter(audience=aud).count()
    Audience.objects.filter(pk=aud.pk).update(size=total, materialized_at=timezone.now())
    return deleted, total


@transaction.atomic
def rebuild_dynamic_audience(audience: Union[Audience, uuid.UUID, str]) -> Tuple[int, int, int]:
    """
    Materialize current rule results into AudienceMembership for a DYNAMIC audience.
    Returns (added, removed, total_now).
    """
    aud = _get_audience_for_update(audience)
    if aud.kind != "DYNAMIC":
        raise ValidationError("rebuild_dynamic_audience only applies to DYNAMIC audiences.")

    # Compute desired set
    desired_qs = evaluate_rules(aud.rules).values_list("id", flat=True)
    desired_ids = set(desired_qs.iterator(chunk_size=CHUNK_SIZE))

    # Current set
    current_ids = set(
        AudienceMembership.objects.filter(audience=aud)
        .values_list("contact_id", flat=True)
        .iterator(chunk_size=CHUNK_SIZE)
    )

    to_add = desired_ids - current_ids
    to_del = current_ids - desired_ids

    # Apply changes
    if to_add:
        payload = (AudienceMembership(audience=aud, contact_id=i) for i in to_add)
        AudienceMembership.objects.bulk_create(payload, ignore_conflicts=True, batch_size=CHUNK_SIZE)

    removed = 0
    if to_del:
        removed, _ = AudienceMembership.objects.filter(audience=aud, contact_id__in=list(to_del)).delete()

    total = AudienceMembership.objects.filter(audience=aud).count()
    Audience.objects.filter(pk=aud.pk).update(size=total, materialized_at=timezone.now())

    return len(to_add), removed, total


# ---------------------------------------------------------------------------
# Campaign domain services
# ---------------------------------------------------------------------------


def fetch_whatsapp_template_requirements(tenant, template_id: str):
    config = get_tenant_config(tenant)
    if not config.whatsapp_integration_enabled:
        return None

    wa = WhatsappBusinessClient(config)
    template = wa.template_details(template_id)
    return template_requirements(template)


def update_template(campaign: Campaign, template_id: str, requirements: Any) -> Dict[str, Any]:
    config = campaign.config or {}
    message_cfg = config.setdefault("message", {})
    message_cfg["whatsapp_template_id"] = template_id
    message_cfg["template_requirements"] = requirements
    campaign.config = config
    campaign.save(update_fields=["config"])
    return {"template_id": template_id, "requirements": requirements}


def update_defaults(campaign: Campaign, defaults_data: Dict[str, Any]) -> Dict[str, Any]:
    config = campaign.config or {}
    defaults = config.setdefault("defaults", {})
    defaults.update(defaults_data)
    campaign.config = config
    campaign.save(update_fields=["config"])
    return defaults


def update_schedule(campaign: Campaign, date_value: Optional[datetime]) -> Dict[str, Any]:
    config = campaign.config or {}
    schedule_cfg = config.setdefault("schedule", {})
    schedule_cfg["date"] = date_value.isoformat() if isinstance(date_value, datetime) else None
    campaign.config = config
    update_fields = ["config"]
    if schedule_cfg.get("date"):
        campaign.status = Status.SCHEDULED
        update_fields.append("status")
    campaign.save(update_fields=update_fields)
    return schedule_cfg


def apply_mapping(
    campaign: Campaign, mapping: List[Dict[str, Any]], contact_field: Optional[str] = None
) -> List[Dict[str, Any]]:
    mapping_payload = list(mapping)
    if contact_field:
        mapping_payload.append(
            {
                "template_var": "contact_name",
                "target_field": contact_field,
                "type": "variable",
            }
        )

    config = campaign.config or {}
    config.setdefault("message", {})["map"] = mapping_payload
    campaign.config = config
    campaign.save(update_fields=["config"])
    return mapping_payload


def clone_campaign(campaign: Campaign) -> Campaign:
    clone_config = remove_keys(campaign.config or {}, ["data_staging"])
    return Campaign.objects.create(
        tenant=campaign.tenant,
        name=f"{campaign.name} (copy)",
        description=campaign.description,
        channel=campaign.channel,
        kind=campaign.kind,
        status=Status.DRAFT,
        audience=campaign.audience,
        config=clone_config,
    )


def launch_campaign(campaign: Campaign) -> List[str | None]:
    job = execute_campaign.apply_async(
        args=[str(campaign.pk)], kwargs={"tenant_id": str(campaign.tenant_id)}
    )
    return [job.id]


def queue_campaign_validation(campaign: Campaign) -> str:
    job = validate_campaign.apply_async(
        args=[str(campaign.pk)],
        queue=settings.MEDIUM_PRIORITY_Q,
        kwargs={"tenant_id": str(campaign.tenant_id)},
    )
    return job.id


def log_campaign_activity(campaign: Campaign, tenant) -> List[Dict[str, Any]]:
    campaign_data = CampaignData.objects.filter(campaign=campaign)

    msg_ids: List[str] = []
    cdo_map = {}
    for cdo in campaign_data:
        result = cdo.result or {}
        messages = result.get("messages") or []
        msg_log = messages[0] if messages else None
        if msg_log:
            wa_id = msg_log.get("id")
            contacts = result.get("contacts") or []
            contact_number = contacts[0].get("input") if contacts else None
            if wa_id:
                msg_ids.append(wa_id)
                cdo_map[wa_id] = {
                    "cdo_id": str(cdo.id),
                    "variables": cdo.variables,
                    "result": result,
                    "contact_number": contact_number,
                }

    qs = (
        WaMessageLog.objects.filter(tenant=tenant, msg_id__in=msg_ids)
        .values("msg_id")
        .annotate(
            sent_time=Max(Case(When(status="sent", then="timestamp"), output_field=DateTimeField())),
            delivered_time=Max(Case(When(status="delivered", then="timestamp"), output_field=DateTimeField())),
            read_time=Max(Case(When(status="read", then="timestamp"), output_field=DateTimeField())),
            failed_time=Max(Case(When(status__in=["failed", "error"], then="timestamp"), output_field=DateTimeField())),
        )
    )

    logs = []
    for entry in qs:
        msg_id = entry["msg_id"]
        cdo_data = cdo_map.get(msg_id, {})
        logs.append(
            {
                "msg_id": msg_id,
                "contact_number": cdo_data.get("contact_number"),
                "timestamps": {
                    "sent": entry["sent_time"],
                    "delivered": entry["delivered_time"],
                    "read": entry["read_time"],
                    "failed": entry["failed_time"],
                },
                "campaign_data": cdo_data,
            }
        )

    return logs

