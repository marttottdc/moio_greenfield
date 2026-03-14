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

from central_hub.integrations.models import IntegrationConfig
from central_hub.integrations.registry import get_integration

from crm.core.activity_capture_contract import ClassificationOutput
from crm.models import (
    ActivityCaptureEntry,
    CaptureEntryAuditEvent,
    CaptureAnchorModel,
    CaptureStatus,
)

logger = logging.getLogger(__name__)


AUTO_APPLY_MIN_CONFIDENCE = 0.85
ADMINISTRATIVE_ANCHOR_ID = "__administrative__"
ADMINISTRATIVE_ANCHOR_ALIASES = {
    ADMINISTRATIVE_ANCHOR_ID,
    "administrative",
    "admin",
    "actividad_administrativa",
}


@dataclass(frozen=True)
class OpenAIConfig:
    api_key: str
    default_model: str
    max_retries: int = 5


def _normalize_anchor_model(anchor_model: str) -> str:
    normalized = (anchor_model or "").strip().lower()
    if normalized in {"crm.administrative", "administrative", "admin"}:
        return CaptureAnchorModel.CONTACT
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
        if (anchor_id or "").strip().lower() in ADMINISTRATIVE_ANCHOR_ALIASES:
            return "Administrative activity"
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
        if (anchor_id or "").strip().lower() in ADMINISTRATIVE_ANCHOR_ALIASES:
            return {}
        return {"contact_id": anchor_id}
    if anchor_model == CaptureAnchorModel.CUSTOMER:
        return {"customer_id": anchor_id}
    return {}


def _activity_anchor_kwargs_with_overrides(
    *,
    entry,
    contact_id_override: str | None = None,
    customer_id_override: str | None = None,
) -> dict:
    """Merge anchor kwargs with optional contact/customer overrides for dual linking."""
    base = _assign_activity_anchor_kwargs(entry.anchor_model, entry.anchor_id)
    if contact_id_override:
        base["contact_id"] = contact_id_override
    if customer_id_override:
        base["customer_id"] = customer_id_override
    return base


def _user_timezone(user) -> str:
    prefs = getattr(user, "preferences", None)
    if isinstance(prefs, dict):
        tz = prefs.get("timezone")
        if isinstance(tz, str) and tz.strip():
            return tz.strip()
    return "UTC"


def _user_language(user) -> str:
    """Return user's preferred language (e.g. en, es, pt) for activity creation."""
    prefs = getattr(user, "preferences", None)
    if isinstance(prefs, dict):
        lang = prefs.get("language")
        if isinstance(lang, str) and lang.strip():
            return lang.strip().lower()[:5]  # e.g. "en", "es", "pt-BR"
    profile = getattr(user, "profile", None)
    if profile and getattr(profile, "locale", None):
        return str(profile.locale).strip().lower()[:5]
    return "en"


def _default_follow_up_datetime(*, user_tz: str) -> datetime:
    """Return a reasonable default for follow-up: ~3 business days from now."""
    from datetime import timedelta

    now = timezone.now()
    # Simple: add 3 days; for production you might skip weekends
    default = now + timedelta(days=3)
    try:
        from zoneinfo import ZoneInfo

        return default.astimezone(ZoneInfo(user_tz))
    except Exception:
        return default


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
    Load OpenAI configuration from IntegrationConfig (slug='openai') only.

    Selection rule:
    - Prefer enabled+configured instance_id='default', else first enabled+configured.
    - If none enabled: accept any configured IntegrationConfig (UI may not set enabled on save).
    """
    if not get_integration("openai"):
        raise ValueError("OpenAI integration is not registered")

    def _from_config(cfg) -> OpenAIConfig:
        api_key = (cfg.config or {}).get("api_key") or ""
        model = (cfg.config or {}).get("default_model") or "gpt-4o-mini"
        max_retries = int((cfg.config or {}).get("max_retries") or 5)
        if not api_key:
            raise ValueError("OpenAI api_key missing in IntegrationConfig")
        return OpenAIConfig(api_key=api_key, default_model=model, max_retries=max_retries)

    # 1. Try IntegrationConfig: enabled=True, is_configured
    qs_enabled = IntegrationConfig.objects.filter(tenant=tenant, slug="openai", enabled=True)
    default_cfg = qs_enabled.filter(instance_id="default").first()
    others = list(qs_enabled.exclude(id=default_cfg.id)) if default_cfg else []
    candidates = [c for c in [default_cfg] if c is not None] + others
    cfg = next((c for c in candidates if c and c.is_configured()), None)
    if cfg:
        return _from_config(cfg)

    # 2. Try any configured IntegrationConfig (enabled may be False if UI did not set it)
    qs_any = IntegrationConfig.objects.filter(tenant=tenant, slug="openai")
    cfg = next((c for c in qs_any if c.is_configured()), None)
    if cfg:
        return _from_config(cfg)

    raise ValueError("OpenAI integration is not configured/enabled for this tenant")


def build_activity_suggestion_prompt(
    *,
    tenant_name: str,
    current_utc_iso: str,
    user_tz: str,
    user_lang: str,
    anchor_model: str,
    anchor_label: str,
    anchor_id: str,
    raw_text: str,
) -> str:
    lang_names = {"es": "Spanish", "en": "English", "pt": "Portuguese", "fr": "French"}
    lang_label = lang_names.get(user_lang.split("-")[0].lower(), "English")
    return (
        "You are Moio, a helpful activity suggester for the CRM of {tenant_name}.\n"
        "Current server time (UTC): {current_utc_iso}\n"
        "User timezone: {user_tz}\n"
        "User language: {user_lang} ({lang_label}). Output all titles, descriptions, reasons in {lang_label}.\n"
        "Anchor record: {anchor_model} \"{anchor_label}\" (ID: {anchor_id})\n\n"
        "TASK: Read the sales note and suggest activities to register in the CRM.\n"
        "Put ALL activities in suggested_activities—this is the ONLY output for activities. One item per activity.\n\n"
        "Activity kinds (use exactly these):\n"
        "- kind 'event': Interactions with contacts (calls, meetings, coffees, visits, messages). Past: status='completed'. Future: status='planned'.\n"
        "  Use proposed_start_at / proposed_end_at. If time vague → needs_time_confirmation=true.\n"
        "- kind 'task': Internal work (prepare presentation, update quote, send docs, review internally).\n"
        "  Use proposed_due_at (usually 1 day before any related meeting if applicable).\n"
        "- kind 'deal': Business opportunity (potential projects, interest in buying, negotiation, possible sale).\n"
        "  Optional: proposed_value (number), proposed_currency (3-letter code).\n\n"
        "Rules:\n"
        "1. Always include a completed 'event' (status='completed') for any past interaction mentioned.\n"
        "2. If a follow-up meeting/review is agreed → add a planned 'event'.\n"
        "3. If preparation is implied (presentation, quote, docs to review/show) → add a 'task' with due before the meeting.\n"
        "4. If multiple opportunities/projects mentioned → create separate 'deal' for each.\n"
        "5. Suggest a follow-up 'event' (planned, ~7 days ahead, needs_time_confirmation=true) when momentum exists but no date set.\n"
        "6. Resolve relative dates to ISO-8601 in {user_tz}.\n"
        "7. List EVERY activity in suggested_activities—past events, tasks, future events, deals. Do not omit any.\n\n"
        "Examples:\n\n"
        "Input: 'Tuve un café con Pedro Suárez, acordamos que preparo la cotización y nos juntamos el jueves para revisarla'\n"
        "→ 3 items in suggested_activities: (1) event 'Café con Pedro Suárez' status=completed, (2) task 'Preparar cotización' proposed_due_at before jueves, (3) event 'Revisión de cotización con Pedro' status=planned start jueves\n\n"
        "Input: 'Tuve una llamada con Carlos, quedamos en revisar una presentación la semana que viene'\n"
        "→ 3 items: completed event (llamada), task (preparar presentación), planned event (revisión)\n\n"
        "Input: 'tomé un cafe con Carla, acordamos juntarnos para revisar la cotizacion el proximo lunes'\n"
        "→ 3 items: completed event (café), task (preparar cotización), planned event (revisión lunes)\n\n"
        "Think step by step: past interactions → preparation tasks → future meetings → opportunities. Then output JSON with full suggested_activities list.\n\n"
        "The sales note is provided as the user input."
    ).format(
        tenant_name=tenant_name,
        current_utc_iso=current_utc_iso,
        user_tz=user_tz,
        user_lang=user_lang,
        lang_label=lang_label,
        anchor_model=anchor_model,
        anchor_label=anchor_label,
        anchor_id=anchor_id,
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

    raw_anchor_model = (anchor_model or "").strip().lower()
    anchor_model_norm = _normalize_anchor_model(anchor_model)
    anchor_id_norm = str(anchor_id or "").strip()
    if anchor_id_norm.lower() in ADMINISTRATIVE_ANCHOR_ALIASES:
        anchor_id_norm = ADMINISTRATIVE_ANCHOR_ID
    if not anchor_id_norm and raw_anchor_model in {"crm.administrative", "administrative", "admin"}:
        anchor_id_norm = ADMINISTRATIVE_ANCHOR_ID
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


def _default_event_datetime(*, user_tz: str) -> Tuple[datetime, datetime]:
    """Ocurrió en una fecha/hora — no hay fin, solo el momento del registro. start == end."""
    now = timezone.now()
    try:
        from zoneinfo import ZoneInfo
        now = now.astimezone(ZoneInfo(user_tz))
    except Exception:
        pass
    return now, now


def _ensure_default_pipeline(tenant):
    """Ensure tenant has a default pipeline (and stages). Creates one if none exists."""
    from crm.models import Pipeline, PipelineStage

    pipeline = Pipeline.objects.filter(tenant=tenant, is_default=True).first()
    if pipeline:
        return pipeline
    # Use any existing pipeline and set it as default if none is default
    pipeline = Pipeline.objects.filter(tenant=tenant).first()
    if pipeline:
        pipeline.is_default = True
        pipeline.save(update_fields=["is_default"])
        return pipeline
    # Create default pipeline with stages
    pipeline = Pipeline.objects.create(
        tenant=tenant,
        name="Sales Pipeline",
        description="Default sales pipeline",
        is_default=True,
    )
    default_stages = [
        {"name": "Qualification", "order": 1, "probability": 10, "color": "#94a3b8"},
        {"name": "Proposal", "order": 2, "probability": 30, "color": "#60a5fa"},
        {"name": "Negotiation", "order": 3, "probability": 60, "color": "#fbbf24"},
        {"name": "Won", "order": 4, "probability": 100, "is_won_stage": True, "color": "#22c55e"},
        {"name": "Lost", "order": 5, "probability": 0, "is_lost_stage": True, "color": "#ef4444"},
    ]
    for stage_data in default_stages:
        PipelineStage.objects.create(tenant=tenant, pipeline=pipeline, **stage_data)
    return pipeline


def _apply_confirmed_activities(
    *,
    confirmed: list[dict[str, Any]],
    entry: ActivityCaptureEntry,
    actor,
    user_tz: str,
    deal_id_override: str | None = None,
    contact_id_override: str | None = None,
    customer_id_override: str | None = None,
) -> dict[str, list[str]]:
    """Create ActivityRecords and Deals from user-confirmed list (task, event, deal)."""
    from crm.services.activity_service import activity_manager
    from crm.models import Deal, Pipeline, PipelineStage

    anchor_kwargs = _activity_anchor_kwargs_with_overrides(
        entry=entry,
        contact_id_override=contact_id_override,
        customer_id_override=customer_id_override,
    )
    activity_ids: list[str] = []
    deal_ids: list[str] = []
    for item in confirmed:
        if not isinstance(item, dict):
            continue
        kind = (item.get("kind") or "event").lower()
        title = (item.get("title") or "").strip() or "Activity"
        description = (item.get("description") or entry.raw_text or "").strip()

        owner_id = item.get("owner_id")
        owner_user = None
        if owner_id and str(owner_id).strip():
            from tenancy.models import MoioUser
            owner_user = MoioUser.objects.filter(tenant=entry.tenant, id=owner_id).first()

        if kind == "task":
            due_at = _parse_iso_dt(item.get("due_at") or item.get("proposed_due_at"), user_tz=user_tz)
            when = due_at or _default_follow_up_datetime(user_tz=user_tz)
            priority = _priority_to_int(item.get("priority"))
            payload = {
                "kind": "task",
                "title": title,
                "content": {
                    "description": description,
                    "due_date": when,
                    "priority": priority,
                    "status": "open",
                },
                "source": "system",
                "visibility": entry.visibility,
                "status": "planned",
                "scheduled_at": when,
                **anchor_kwargs,
            }
            if deal_id_override:
                payload["deal_id"] = deal_id_override
            if owner_user:
                payload["owner_id"] = str(owner_user.id)
            activity = activity_manager.create_activity(
                payload,
                tenant=entry.tenant,
                user=actor,
                activity_type=None,
            )
        elif kind == "event":
            start_at = _parse_iso_dt(item.get("start_at") or item.get("proposed_start_at"), user_tz=user_tz)
            end_at = _parse_iso_dt(item.get("end_at") or item.get("proposed_end_at"), user_tz=user_tz)
            if not start_at or not end_at:
                # El evento se asume en la fecha/hora en que se está registrando
                start_at, end_at = _default_event_datetime(user_tz=user_tz)
            duration_minutes = max(0, int((end_at - start_at).total_seconds() // 60))
            participants = item.get("attendees") or item.get("participants") or []
            if isinstance(participants, list):
                participants = [str(p) for p in participants if p]
            status = (item.get("status") or "planned").lower()
            if status not in ("planned", "completed"):
                status = "planned"
            payload = {
                "kind": "event",
                "title": title,
                "content": {
                    "start": start_at,
                    "end": end_at,
                    "location": item.get("location"),
                    "participants": participants,
                },
                "source": "system",
                "visibility": entry.visibility,
                "status": status,
                "scheduled_at": start_at,
                "duration_minutes": duration_minutes,
                **anchor_kwargs,
            }
            if deal_id_override:
                payload["deal_id"] = deal_id_override
            # Eventos: el autor (actor) es el responsable; no se asigna owner_id distinto
            activity = activity_manager.create_activity(
                payload,
                tenant=entry.tenant,
                user=actor,
                activity_type=None,
            )
        elif kind == "deal":
            contact_id = anchor_kwargs.get("contact_id")
            customer_id = anchor_kwargs.get("customer_id")
            pipeline = Pipeline.objects.filter(tenant=entry.tenant, is_default=True).first()
            if pipeline is None:
                pipeline = _ensure_default_pipeline(entry.tenant)
            stage = None
            if pipeline:
                stage = PipelineStage.objects.filter(pipeline=pipeline).order_by("order").first()
            from decimal import Decimal
            value = Decimal("0")
            if item.get("proposed_value"):
                try:
                    value = Decimal(str(item["proposed_value"]))
                except Exception:
                    pass
            currency = (item.get("proposed_currency") or "USD").strip()[:3]
            deal = Deal.objects.create(
                tenant=entry.tenant,
                title=title,
                description=description or "",
                contact_id=contact_id,
                customer_id=customer_id,
                pipeline=pipeline,
                stage=stage,
                value=value,
                currency=currency,
                status="open",
                created_by=actor,
                owner=actor,
            )
            deal_ids.append(str(deal.id))
            continue
        else:
            continue

        activity.originating_capture_entry = entry
        activity.save(update_fields=["originating_capture_entry"])
        activity_ids.append(str(activity.id))

    return {"activity_record_ids": activity_ids, "deal_ids": deal_ids}


def apply_capture_entry_to_activities(
    *,
    entry: ActivityCaptureEntry,
    actor,
    deal_id_override: str | None = None,
    contact_id_override: str | None = None,
    customer_id_override: str | None = None,
) -> dict[str, Any]:
    """
    Create canonical ActivityRecord rows from entry.final/classification.
    Returns dict with applied refs.
    When both contact and customer are provided (anchor + override), ensures CustomerContact link exists.
    """
    from crm.services.activity_service import activity_manager
    from crm.models import CustomerContact, Contact, Customer

    # Resolve final contact_id and customer_id (anchor + overrides)
    anchor_kwargs = _activity_anchor_kwargs_with_overrides(
        entry=entry,
        contact_id_override=contact_id_override,
        customer_id_override=customer_id_override,
    )
    contact_id = anchor_kwargs.get("contact_id")
    customer_id = anchor_kwargs.get("customer_id")

    # Link contact to account (CustomerContact) when both are provided
    if contact_id and customer_id:
        try:
            contact = Contact.objects.filter(tenant=entry.tenant).filter(
                Q(pk=contact_id) | Q(user_id=contact_id)
            ).first()
            if contact and Customer.objects.filter(tenant=entry.tenant, id=customer_id).exists():
                CustomerContact.objects.get_or_create(
                    tenant=entry.tenant,
                    contact=contact,
                    customer_id=customer_id,
                    defaults={"role": ""},
                )
        except Exception:
            pass  # Don't fail apply if linking fails

    classification = entry.final or entry.classification or {}
    if not isinstance(classification, dict):
        classification = {}

    user_tz = _user_timezone(actor)

    # User-confirmed activities (from apply-sync with user edits)
    confirmed = classification.get("confirmed_activities")
    if isinstance(confirmed, list) and confirmed:
        result = _apply_confirmed_activities(
            confirmed=confirmed,
            entry=entry,
            actor=actor,
            user_tz=user_tz,
            deal_id_override=deal_id_override,
            contact_id_override=contact_id_override,
            customer_id_override=customer_id_override,
        )
        if result["activity_record_ids"] or result["deal_ids"]:
            return {"activity_record_ids": result["activity_record_ids"], "deal_ids": result["deal_ids"]}

    # suggested_activities is the single source of truth (from classification or entry)
    suggested = classification.get("suggested_activities")
    if not suggested and hasattr(entry, "suggested_activities") and entry.suggested_activities:
        suggested = entry.suggested_activities
    if isinstance(suggested, list) and suggested:
        to_apply = [
            dict(item) if isinstance(item, dict) else {}
            for item in suggested
            if isinstance(item, dict) and item.get("kind")
        ]
        if to_apply:
            result = _apply_confirmed_activities(
                confirmed=to_apply,
                entry=entry,
                actor=actor,
                user_tz=user_tz,
                deal_id_override=deal_id_override,
                contact_id_override=contact_id_override,
                customer_id_override=customer_id_override,
            )
            if result["activity_record_ids"] or result["deal_ids"]:
                return {"activity_record_ids": result["activity_record_ids"], "deal_ids": result["deal_ids"]}

    # Default fallback: single past event (e.g. note-only)
    fallback_anchor = _activity_anchor_kwargs_with_overrides(
        entry=entry,
        contact_id_override=contact_id_override,
        customer_id_override=customer_id_override,
    )

    def _create_past_event(title: str, body: str = ""):
        start_at, end_at = _default_event_datetime(user_tz=user_tz)
        duration_minutes = max(0, int((end_at - start_at).total_seconds() // 60))
        payload = {
            "kind": "event",
            "title": title or "Event",
            "content": {"start": start_at, "end": end_at, "location": None, "participants": []},
            "source": "system",
            "visibility": entry.visibility,
            "status": "completed",
            "scheduled_at": start_at,
            "duration_minutes": duration_minutes,
            **fallback_anchor,
        }
        if deal_id_override:
            payload["deal_id"] = deal_id_override
        activity = activity_manager.create_activity(
            payload,
            tenant=entry.tenant,
            user=actor,
            activity_type=None,
        )
        activity.originating_capture_entry = entry
        activity.save(update_fields=["originating_capture_entry"])
        return str(activity.id)

    title = (classification.get("summary") or "").strip() or "Event"
    aid = _create_past_event(title=title, body=entry.raw_text or "")
    return {"activity_record_ids": [aid], "deal_ids": []}


def _suggested_item_to_proposed(item: dict[str, Any], user_tz: str, summary: str, raw_text: str) -> dict[str, Any]:
    """Convert SuggestedActivityItem dict to proposed activity format for UI."""
    kind = (item.get("kind") or "event").lower()
    if kind not in ("task", "event", "deal"):
        kind = "event"
    title = (item.get("title") or "").strip() or "Activity"
    desc = (item.get("description") or summary or raw_text or "").strip()
    if kind == "task":
        due_at = _parse_iso_dt(item.get("proposed_due_at"), user_tz=user_tz)
        return {
            "kind": "task",
            "title": title,
            "description": desc,
            "due_at": due_at.isoformat() if due_at else None,
            "priority": item.get("priority") or "MEDIUM",
            "reason": item.get("reason"),
            "needs_time_confirmation": bool(item.get("needs_time_confirmation")),
        }
    if kind == "event":
        start_at = _parse_iso_dt(item.get("proposed_start_at"), user_tz=user_tz)
        end_at = _parse_iso_dt(item.get("proposed_end_at"), user_tz=user_tz)
        return {
            "kind": "event",
            "title": title,
            "description": desc,
            "status": (item.get("status") or "planned").lower(),
            "start_at": start_at.isoformat() if start_at else None,
            "end_at": end_at.isoformat() if end_at else None,
            "location": item.get("location"),
            "attendees": item.get("attendees") or [],
            "reason": item.get("reason"),
            "needs_time_confirmation": bool(item.get("needs_time_confirmation")),
        }
    if kind == "deal":
        return {
            "kind": "deal",
            "title": title,
            "description": desc,
            "proposed_value": item.get("proposed_value"),
            "proposed_currency": item.get("proposed_currency") or "USD",
            "reason": item.get("reason"),
        }
    return {"kind": "event", "title": title, "description": desc}


def build_proposed_activity_from_classification(
    *,
    entry: ActivityCaptureEntry,
    classification: dict[str, Any],
    user_tz: str,
) -> dict[str, Any]:
    """
    Build a preview payload of what would be created by apply_capture_entry_to_activities.
    Returns suggested_activities (list for user to confirm/edit) and proposed_activity (first for backward compat).
    """
    summary = (classification.get("summary") or "").strip() or (entry.raw_text or "")[:500]
    raw_text = entry.raw_text or ""

    # Primary: use suggested_activities from classification or entry (stored on capture record)
    suggested = classification.get("suggested_activities")
    if not suggested and hasattr(entry, "suggested_activities") and entry.suggested_activities:
        suggested = entry.suggested_activities
    if isinstance(suggested, list) and suggested:
        activities = [
            _suggested_item_to_proposed(item, user_tz=user_tz, summary=summary, raw_text=raw_text)
            for item in suggested
            if isinstance(item, dict) and item.get("kind")
        ]
        if activities:
            primary = activities[0]
            return {
                "suggested_activities": activities,
                "proposed_activities": activities,
                "proposed_activity": primary,
            }

    # Fallback: single event when suggested_activities is empty
    title = (summary or "Event").strip() or "Event"
    activities = [{"kind": "event", "title": title, "description": entry.raw_text or summary, "status": "completed"}]
    primary = activities[0]
    return {
        "suggested_activities": activities,
        "proposed_activities": activities,
        "proposed_activity": primary,
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
        from central_hub.integrations.v1.services.accounts import visible_calendar_accounts
        from central_hub.integrations.v1.services import calendar_service
        from central_hub.rbac import user_has_role
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
    user_lang = _user_language(actor)
    anchor_label = _resolve_anchor_label(
        tenant=tenant, anchor_model=entry.anchor_model, anchor_id=entry.anchor_id
    )
    cfg = get_openai_config_for_tenant(tenant=tenant)

    prompt = build_activity_suggestion_prompt(
        tenant_name=getattr(tenant, "nombre", None) or getattr(tenant, "name", None) or str(tenant),
        current_utc_iso=timezone.now().astimezone(dt_timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        user_tz=user_tz,
        user_lang=user_lang,
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
            "suggested_activities": [{"kind": "event", "title": summary[:80] or "Event", "reason": "Fallback"}],
            "temporal_type": "ambiguous",
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
    # Responses API requires non-empty input; pass raw_text as input.
    step1_error: Optional[str] = None
    try:
        return client.structured_parse_via_responses(
            data=entry.raw_text or " ",
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

