from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Optional, Tuple

from django.db import transaction
from django.db.models import Q
from datetime import timezone as dt_timezone
from django.utils import timezone

from portal.integrations.models import IntegrationConfig
from portal.integrations.registry import get_integration

from crm.core.activity_capture_contract import ClassificationOutput
from crm.models import (
    ActivityCaptureEntry,
    CaptureEntryAuditEvent,
    CaptureAnchorModel,
    CaptureStatus,
)

logger = logging.getLogger(__name__)


AUTO_APPLY_MIN_CONFIDENCE = 0.85


@dataclass(frozen=True)
class OpenAIConfig:
    api_key: str
    default_model: str
    max_retries: int = 5


def _normalize_anchor_model(anchor_model: str) -> str:
    normalized = (anchor_model or "").strip().lower()
    if normalized in {"crm.account", "crm.company", "crm.organization", "crm.client"}:
        normalized = CaptureAnchorModel.CUSTOMER
    if normalized in {CaptureAnchorModel.DEAL, CaptureAnchorModel.CONTACT, CaptureAnchorModel.CUSTOMER}:
        return normalized
    raise ValueError(f"Invalid anchor_model: {anchor_model}")


def _resolve_anchor_label(*, tenant, anchor_model: str, anchor_id: str) -> str:
    """
    Resolve a stable label for prompt context.
    Validates the anchor belongs to the tenant.
    """
    from crm.models import Contact, Deal, Customer

    if anchor_model == CaptureAnchorModel.DEAL:
        deal = Deal.objects.filter(tenant=tenant, id=anchor_id).first()
        if not deal:
            raise ValueError("Anchor deal not found")
        return deal.title
    if anchor_model == CaptureAnchorModel.CONTACT:
        contact = Contact.objects.filter(tenant=tenant).filter(Q(pk=anchor_id) | Q(user_id=anchor_id)).first()
        if not contact:
            raise ValueError("Anchor contact not found")
        return contact.display_name or contact.fullname or contact.whatsapp_name or contact.email or contact.phone or str(contact.user_id)
    if anchor_model == CaptureAnchorModel.CUSTOMER:
        customer = Customer.objects.filter(tenant=tenant, id=anchor_id).first()
        if not customer:
            raise ValueError("Anchor customer not found")
        return customer.name or customer.legal_name or str(customer.id)
    raise ValueError(f"Unsupported anchor_model: {anchor_model}")


def _assign_activity_anchor_kwargs(anchor_model: str, anchor_id: str) -> dict:
    # ActivityRecord anchors are explicit FKs
    if anchor_model == CaptureAnchorModel.DEAL:
        return {"deal_id": anchor_id}
    if anchor_model == CaptureAnchorModel.CONTACT:
        return {"contact_id": anchor_id}
    if anchor_model == CaptureAnchorModel.CUSTOMER:
        return {"customer_id": anchor_id}
    return {}


def _user_timezone(user) -> str:
    prefs = getattr(user, "preferences", None)
    if isinstance(prefs, dict):
        tz = prefs.get("timezone")
        if isinstance(tz, str) and tz.strip():
            return tz.strip()
    return "UTC"


def _parse_iso_dt(value: Optional[str], *, user_tz: str) -> Optional[datetime]:
    if not value:
        return None
    raw = str(value).strip()
    if not raw:
        return None
    # Use stdlib parsing for ISO-8601 variants
    # - If naive, assume user timezone.
    try:
        if raw.endswith("Z"):
            raw = raw[:-1] + "+00:00"
        dt = datetime.fromisoformat(raw)
    except Exception:
        return None

    if timezone.is_naive(dt):
        try:
            from zoneinfo import ZoneInfo

            dt = timezone.make_aware(dt, ZoneInfo(user_tz))
        except Exception:
            dt = timezone.make_aware(dt, dt_timezone.utc)
    return dt


def _priority_to_int(priority: Optional[str]) -> int:
    p = (priority or "").upper().strip()
    if p == "HIGH":
        return 5
    if p == "MEDIUM":
        return 3
    if p == "LOW":
        return 2
    return 3


def _audit(entry: ActivityCaptureEntry, *, actor=None, event_type: str, event_data: dict[str, Any]) -> None:
    CaptureEntryAuditEvent.objects.create(
        tenant=entry.tenant,
        entry=entry,
        actor=actor,
        event_type=event_type,
        event_data=event_data or {},
    )


def get_openai_config_for_tenant(*, tenant) -> OpenAIConfig:
    """
    Load OpenAI configuration from IntegrationConfig (slug='openai').

    Selection rule:
    - Prefer enabled+configured instance_id='default' if present.
    - Else first enabled+configured instance.
    """
    # Ensure the integration exists in registry (guard against removed registry entries)
    if not get_integration("openai"):
        raise ValueError("OpenAI integration is not registered")

    qs = IntegrationConfig.objects.filter(tenant=tenant, slug="openai", enabled=True)
    default_cfg = qs.filter(instance_id="default").first()
    candidates = [c for c in [default_cfg] if c is not None] + list(qs.exclude(id=getattr(default_cfg, "id", None)))
    cfg = next((c for c in candidates if c.is_configured()), None)
    if not cfg:
        raise ValueError("OpenAI integration is not configured/enabled for this tenant")

    api_key = cfg.config.get("api_key") or ""
    model = cfg.config.get("default_model") or "gpt-4o-mini"
    max_retries = int(cfg.config.get("max_retries") or 5)
    if not api_key:
        raise ValueError("OpenAI api_key missing in IntegrationConfig")
    return OpenAIConfig(api_key=api_key, default_model=model, max_retries=max_retries)


def build_system_prompt(
    *,
    tenant_name: str,
    current_utc_iso: str,
    user_tz: str,
    anchor_model: str,
    anchor_label: str,
    anchor_id: str,
    raw_text: str,
) -> str:
    return (
        "You are Moio, a precise CRM activity classifier for {tenant_name}.\n"
        "Current server time (UTC): {current_utc_iso}\n"
        "User timezone: {user_tz}\n"
        "Anchor record: {anchor_model} \"{anchor_label}\" (ID: {anchor_id})\n\n"
        "Classify the sales note below. Resolve relative dates/times into full ISO strings using the user's timezone.\n"
        "If any date/time or entity is ambiguous, set needs_review=true and list clear reasons.\n"
        "Output ONLY valid JSON matching the ClassificationOutput schema.\n\n"
        "Sales note:\n"
        "\"\"\"{raw_text}\"\"\"\n"
    ).format(
        tenant_name=tenant_name,
        current_utc_iso=current_utc_iso,
        user_tz=user_tz,
        anchor_model=anchor_model,
        anchor_label=anchor_label,
        anchor_id=anchor_id,
        raw_text=raw_text,
    )


def create_capture_entry(
    *,
    raw_text: str,
    anchor_model: str,
    anchor_id: str,
    actor,
    raw_source: str = "manual_text",
    channel_hint: Optional[str] = None,
    visibility: Optional[str] = None,
    idempotency_key: Optional[str] = None,
) -> Tuple[ActivityCaptureEntry, bool]:
    tenant = getattr(actor, "tenant", None)
    if not tenant:
        raise ValueError("tenant_required")

    raw_text_norm = (raw_text or "").strip()
    if not raw_text_norm:
        raise ValueError("raw_text_required")

    anchor_model_norm = _normalize_anchor_model(anchor_model)
    anchor_id_norm = str(anchor_id or "").strip()
    if not anchor_id_norm:
        raise ValueError("anchor_id_required")

    # Validate anchor exists (and capture label for prompt later).
    _resolve_anchor_label(tenant=tenant, anchor_model=anchor_model_norm, anchor_id=anchor_id_norm)

    with transaction.atomic():
        if idempotency_key:
            existing = ActivityCaptureEntry.objects.filter(
                tenant=tenant, idempotency_key=idempotency_key
            ).first()
            if existing:
                return existing, False

        entry = ActivityCaptureEntry.objects.create(
            tenant=tenant,
            actor=actor,
            anchor_model=anchor_model_norm,
            anchor_id=anchor_id_norm,
            raw_text=raw_text_norm,
            raw_source=raw_source or "manual_text",
            channel_hint=channel_hint or None,
            visibility=visibility or ActivityCaptureEntry._meta.get_field("visibility").default,
            status=CaptureStatus.CAPTURED,
            idempotency_key=idempotency_key or None,
        )
        _audit(entry, actor=actor, event_type="captured", event_data={"raw_source": entry.raw_source})
        return entry, True


def apply_capture_entry_to_activities(*, entry: ActivityCaptureEntry, actor) -> dict[str, Any]:
    """
    Create canonical ActivityRecord rows from entry.final/classification.
    Returns dict with applied refs.
    """
    from crm.services.activity_service import activity_manager

    classification = entry.final or entry.classification or {}
    if not isinstance(classification, dict):
        classification = {}

    user_tz = _user_timezone(actor)
    applied: list[str] = []

    # Always allow “note-only” fallback when asked, or when no structured intent exists.
    intent = (classification.get("intent") or {}) if isinstance(classification.get("intent"), dict) else {}

    def _create_note(body: str, title: str):
        activity = activity_manager.create_activity(
            {
                "kind": "note",
                "title": title or "Note",
                "content": {"body": body, "tags": []},
                "source": "manual",
                "visibility": entry.visibility,
                "status": "completed",
                **_assign_activity_anchor_kwargs(entry.anchor_model, entry.anchor_id),
            },
            tenant=entry.tenant,
            user=actor,
            activity_type=None,
        )
        activity.originating_capture_entry = entry
        activity.save(update_fields=["originating_capture_entry"])
        applied.append(str(activity.id))

    # Task intent
    create_task = intent.get("create_task") if isinstance(intent, dict) else None
    if isinstance(create_task, dict) and create_task.get("do") is True:
        title = (create_task.get("title") or classification.get("summary") or "").strip() or "Follow-up"
        due_at = _parse_iso_dt(create_task.get("due_at"), user_tz=user_tz)
        if due_at is None:
            # If missing/invalid date, fallback to needs-review behavior at higher level
            raise ValueError("task_due_at_missing")
        priority = _priority_to_int(create_task.get("priority"))
        activity = activity_manager.create_activity(
            {
                "kind": "task",
                "title": title,
                "content": {
                    "description": classification.get("summary") or entry.raw_text,
                    "due_date": due_at,
                    "priority": priority,
                    "status": "open",
                },
                "source": "system",
                "visibility": entry.visibility,
                "status": "planned",
                "scheduled_at": due_at,
                **_assign_activity_anchor_kwargs(entry.anchor_model, entry.anchor_id),
            },
            tenant=entry.tenant,
            user=actor,
            activity_type=None,
        )
        activity.originating_capture_entry = entry
        activity.save(update_fields=["originating_capture_entry"])
        applied.append(str(activity.id))

    # Appointment intent (maps to ActivityRecord kind='event')
    create_appt = intent.get("create_appointment") if isinstance(intent, dict) else None
    if isinstance(create_appt, dict) and create_appt.get("do") is True:
        title = (create_appt.get("title") or classification.get("summary") or "").strip() or "Meeting"
        start_at = _parse_iso_dt(create_appt.get("start_at"), user_tz=user_tz)
        end_at = _parse_iso_dt(create_appt.get("end_at"), user_tz=user_tz)
        if not start_at or not end_at:
            raise ValueError("appointment_time_missing")

        if bool(create_appt.get("book_calendar")) is True:
            # Commit-time conflict check against connected calendars.
            if has_calendar_conflicts(user=actor, start_at=start_at, end_at=end_at):
                raise ValueError("calendar_conflict_detected")
        duration_minutes = max(0, int((end_at - start_at).total_seconds() // 60))
        attendees = create_appt.get("attendees")
        participants: list[str] = []
        if isinstance(attendees, list):
            for a in attendees:
                if isinstance(a, dict):
                    email = a.get("email") or a.get("address")
                    if email:
                        participants.append(str(email))
        activity = activity_manager.create_activity(
            {
                "kind": "event",
                "title": title,
                "content": {
                    "start": start_at,
                    "end": end_at,
                    "location": create_appt.get("location"),
                    "participants": participants,
                },
                "source": "system",
                "visibility": entry.visibility,
                "status": "planned",
                "scheduled_at": start_at,
                "duration_minutes": duration_minutes or None,
                **_assign_activity_anchor_kwargs(entry.anchor_model, entry.anchor_id),
            },
            tenant=entry.tenant,
            user=actor,
            activity_type=None,
        )
        activity.originating_capture_entry = entry
        activity.save(update_fields=["originating_capture_entry"])
        applied.append(str(activity.id))

    if not applied:
        # Default behavior: store as a note
        title = (classification.get("summary") or "").strip() or "Note"
        _create_note(entry.raw_text, title=title)

    return {"activity_record_ids": applied}


def build_proposed_activity_from_classification(
    *,
    entry: ActivityCaptureEntry,
    classification: dict[str, Any],
    user_tz: str,
) -> dict[str, Any]:
    """
    Build a preview payload of what would be created by apply_capture_entry_to_activities.
    Does not create any ActivityRecord. Used for sync classify + confirm flow.
    """
    intent = (classification.get("intent") or {}) if isinstance(classification.get("intent"), dict) else {}
    summary = (classification.get("summary") or "").strip() or (entry.raw_text or "")[:500]
    create_task = intent.get("create_task") if isinstance(intent.get("create_task"), dict) else None
    create_appt = intent.get("create_appointment") if isinstance(intent.get("create_appointment"), dict) else None

    if create_task and create_task.get("do") is True:
        due_at = _parse_iso_dt(create_task.get("due_at"), user_tz=user_tz)
        title = (create_task.get("title") or summary or "").strip() or "Follow-up"
        return {
            "kind": "task",
            "title": title,
            "due_at": due_at.isoformat() if due_at else None,
            "priority": create_task.get("priority") or "MEDIUM",
            "description": summary or entry.raw_text,
        }

    if create_appt and create_appt.get("do") is True:
        start_at = _parse_iso_dt(create_appt.get("start_at"), user_tz=user_tz)
        end_at = _parse_iso_dt(create_appt.get("end_at"), user_tz=user_tz)
        title = (create_appt.get("title") or summary or "").strip() or "Meeting"
        return {
            "kind": "event",
            "title": title,
            "start_at": start_at.isoformat() if start_at else None,
            "end_at": end_at.isoformat() if end_at else None,
            "location": create_appt.get("location"),
            "attendees": create_appt.get("attendees") or [],
        }

    title = (summary or "Note").strip() or "Note"
    return {
        "kind": "note",
        "title": title,
        "body": entry.raw_text or summary,
    }


def has_calendar_conflicts(*, user, start_at: datetime, end_at: datetime) -> bool:
    """
    Best-effort free/busy check using the existing calendar integrations.

    Current implementation:
    - Checks user-owned accounts for the user
    - Checks tenant-owned accounts only if user is tenant_admin/superuser
    - Treats any event returned in the range as a conflict
    """
    try:
        from portal.integrations.v1.services.accounts import visible_calendar_accounts
        from portal.integrations.v1.services import calendar_service
        from portal.rbac import user_has_role
    except Exception:
        return False

    qs = visible_calendar_accounts(user).select_related("external_account", "tenant")
    if not (getattr(user, "is_superuser", False) or user_has_role(user, "tenant_admin")):
        qs = qs.filter(external_account__ownership="user", external_account__owner_user=user)

    start_iso = start_at.astimezone(dt_timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    end_iso = end_at.astimezone(dt_timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")

    for account in qs:
        try:
            items, _next = calendar_service.list_events(
                account,
                start=start_iso,
                end=end_iso,
                cursor=None,
                page_size=5,
            )
            if items:
                return True
        except Exception:
            # Fail open: never block apply due to an integrations outage.
            continue
    return False


def classify_entry_via_openai(*, entry: ActivityCaptureEntry) -> ClassificationOutput:
    from moio_platform.lib.openai_gpt_api import MoioOpenai

    tenant = entry.tenant
    actor = entry.actor

    user_tz = _user_timezone(actor)
    anchor_label = _resolve_anchor_label(
        tenant=tenant, anchor_model=entry.anchor_model, anchor_id=entry.anchor_id
    )
    cfg = get_openai_config_for_tenant(tenant=tenant)

    prompt = build_system_prompt(
        tenant_name=getattr(tenant, "nombre", None) or getattr(tenant, "name", None) or str(tenant),
        current_utc_iso=timezone.now().astimezone(dt_timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        user_tz=user_tz,
        anchor_model=entry.anchor_model,
        anchor_label=anchor_label,
        anchor_id=entry.anchor_id,
        raw_text=entry.raw_text,
    )

    client = MoioOpenai(api_key=cfg.api_key, default_model=cfg.default_model, max_retries=cfg.max_retries)

    def _fallback(*, reasons: list[str]) -> ClassificationOutput:
        raw_text = (entry.raw_text or "").strip()
        summary = (raw_text[:240] + "…") if len(raw_text) > 240 else (raw_text or "Note")
        payload = {
            "summary": summary,
            "channel": "OTHER",
            "direction": "INTERNAL",
            "outcome": "UNKNOWN",
            "intent": {"create_task": {"do": False}, "create_appointment": {"do": False}},
            "suggest_links": [],
            "needs_review": True,
            "review_reasons": [r for r in reasons if r],
            "confidence": 0.0,
        }
        return ClassificationOutput.model_validate(payload)

    model = cfg.default_model
    if not client.model_supports_structured_outputs(model):
        note = "Configured Model does not support structured Outputs"
        logger.error("%s (model=%s)", note, model)
        raise ValueError(note)

    # Step 1: try Responses API first (recommended; better caching/cost), then Completions.
    step1_error: Optional[str] = None
    try:
        return client.structured_parse_via_responses(
            data="",
            system_instructions=prompt,
            output_model=ClassificationOutput,
            model=model,
            max_retries=cfg.max_retries,
        )
    except (AttributeError, ValueError) as exc:
        step1_error = str(exc)
        logger.debug("Responses API parse not used (%s); trying Completions", step1_error)
    except Exception as exc:
        step1_error = str(exc)
        logger.warning("Structured classification (Responses API) failed; trying Completions", exc_info=True)

    try:
        return client.structured_parse(
            data="",
            system_instructions=prompt,
            output_model=ClassificationOutput,
            model=model,
            store=False,
            max_retries=cfg.max_retries,
        )
    except Exception as exc:
        step1_error = str(exc)
        logger.warning("Structured classification (Completions) failed; attempting 2-step repair", exc_info=True)

    # Step 2: best-effort JSON mode classification, then strict repair into schema.
    try:
        raw = client.json_response(
            data="",
            system_instructions=prompt,
            max_retries=cfg.max_retries,
        )
        if raw is None:
            raise ValueError("openai_no_response")
        if isinstance(raw, Exception):
            raise ValueError(f"openai_error:{str(raw)}")

        repair_instructions = (
            prompt
            + "\n\n"
            + "You will be given a previous attempt that may not match the schema.\n"
            + "Transform it into a valid JSON object matching the ClassificationOutput schema EXACTLY.\n"
            + "Do not add extra keys. If information is missing/ambiguous, set needs_review=true and explain in review_reasons.\n"
        )
        return client.structured_parse(
            data=f"Previous output:\n{raw}",
            system_instructions=repair_instructions,
            output_model=ClassificationOutput,
            model=model,
            store=False,
            max_retries=cfg.max_retries,
        )
    except Exception as exc2:
        logger.exception("Repair classification failed; using deterministic needs-review fallback")
        return _fallback(reasons=[f"structured_output_failed:{step1_error}", f"repair_failed:{str(exc2)}"])

