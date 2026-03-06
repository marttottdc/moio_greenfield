"""
Event Emitter API.

Provides the emit_event() function for emitting events from business logic.
Events are persisted and asynchronously routed to matching flows.
"""

from __future__ import annotations

import logging
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Optional
from uuid import UUID

from django.db import transaction
from django.utils import timezone
from jsonschema import Draft202012Validator
from jsonschema.exceptions import ValidationError as JsonSchemaValidationError

from .schemas import get_event_payload_schema
from .snapshots import snapshot_contact, snapshot_deal

logger = logging.getLogger(__name__)


def _contact_snapshot(contact) -> dict:
    """Serialize a minimal, stable contact snapshot for event payloads."""
    return snapshot_contact(contact)


def _maybe_enrich_payload(name: str, tenant_id: UUID, payload: dict) -> dict:
    """
    Best-effort enrichment for event payloads.

    Adds:
    - contact snapshots when contact identifiers are present
    - deal description/contact_id when deal_id is present
    """
    if not isinstance(payload, dict) or not payload:
        return payload or {}

    # Avoid circular imports / optional modules in minimal deployments.
    try:
        from django.db.models import Q
        from crm.models import Contact, Deal
    except Exception:  # pragma: no cover
        return payload

    def _load_contact(contact_identifier):
        if not contact_identifier:
            return None
        qs = Contact.objects.select_related("ctype", "tenant").filter(tenant__tenant_code=tenant_id)
        return qs.filter(Q(pk=contact_identifier) | Q(user_id=contact_identifier)).first()

    # Enrich contacts by common keys.
    contact_key_map = {
        "contact_id": "contact",
        "creator_id": "creator",
        "assigned_id": "assigned",
        "waiting_for_id": "waiting_for",
    }
    for id_key, obj_key in contact_key_map.items():
        if id_key in payload and obj_key not in payload:
            contact_obj = _load_contact(payload.get(id_key))
            if contact_obj is not None:
                    payload[obj_key] = snapshot_contact(contact_obj)

    # Enrich deal fields if a deal id is provided.
    if payload.get("deal_id") and (payload.get("description") is None or payload.get("contact_id") is None):
        try:
            deal = Deal.objects.select_related("contact", "tenant", "contact__ctype").filter(
                tenant__tenant_code=tenant_id,
                id=payload.get("deal_id"),
            ).first()
            if deal is not None:
                if payload.get("description") is None:
                    payload["description"] = getattr(deal, "description", None) or ""
                if payload.get("contact_id") is None and getattr(deal, "contact_id", None):
                    payload["contact_id"] = str(deal.contact_id)
                # Prefer a nested deal snapshot, and also include contact snapshot for convenience.
                if "deal" not in payload:
                    payload["deal"] = snapshot_deal(deal, include_contact=True)
                if getattr(deal, "contact", None) is not None and "contact" not in payload:
                    payload["contact"] = snapshot_contact(deal.contact)
        except Exception:
            # Never fail emission on enrichment issues.
            pass

    return payload


def serialize_value(value: Any) -> Any:
    """Convert a value to JSON-serializable format."""
    if value is None:
        return None
    if isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (list, tuple)):
        return [serialize_value(v) for v in value]
    if isinstance(value, dict):
        return {k: serialize_value(v) for k, v in value.items()}
    return str(value)


def _normalize_payload(payload) -> dict:
    """Recursively serialize all values in the payload."""
    if payload is None:
        return {}
    if not isinstance(payload, dict):
        return {"value": serialize_value(payload)}
    return {k: serialize_value(v) for k, v in payload.items()}


def _create_event_log(
    name: str,
    tenant_id: UUID,
    actor: Optional[dict] = None,
    entity: Optional[dict] = None,
    payload: Optional[dict] = None,
    source: str = "",
    correlation_id: Optional[UUID] = None,
    occurred_at: Optional[datetime] = None,
):
    """Create and persist an EventLog entry."""
    from flows.models import EventLog
    
    event = EventLog.objects.create(
        name=name,
        tenant_id=tenant_id,
        actor=_normalize_payload(actor) if actor else None,
        entity=_normalize_payload(entity) if entity else None,
        payload=_normalize_payload(payload or {}),
        source=source,
        correlation_id=correlation_id,
        occurred_at=occurred_at or timezone.now(),
    )
    
    logger.info(f"Event emitted: {name} (id={event.id}, tenant={tenant_id})")
    return event


def _dispatch_to_router(event_id: UUID):
    """Dispatch event to router for flow matching (async via Celery)."""
    try:
        from .tasks import route_event_task
        from moio_platform.settings import FLOWS_Q

        # Ensure event routing lands on the flows queue (some deployments do not consume the default queue).
        route_event_task.apply_async(args=[str(event_id)], queue=FLOWS_Q)
    except ImportError:
        logger.warning("Event routing task not available, routing synchronously")
        from .router import route_event
        route_event(event_id)


def emit_event(
    name: str,
    tenant_id: UUID,
    *,
    actor: Optional[dict] = None,
    entity: Optional[dict] = None,
    payload: Optional[dict] = None,
    source: str = "api",
    correlation_id: Optional[UUID] = None,
    occurred_at: Optional[datetime] = None,
    defer_routing: bool = True,
) -> UUID:
    """
    Emit an event and route it to matching flows.
    
    This is the primary API for emitting events from business logic.
    Events are persisted immediately and routed to flows asynchronously
    via transaction.on_commit to ensure data consistency.
    
    Args:
        name: Event name in format entity.action (e.g., deal.won)
        tenant_id: UUID of the tenant that owns this event
        actor: Optional dict describing who triggered the event
               {"type": "user"|"system"|"service", "id": "uuid"}
        entity: Optional dict describing the primary entity affected
                {"type": "deal"|"contact"|..., "id": "uuid"}
        payload: Arbitrary structured event data
        source: Source that emitted the event (api, task, webhook, etc.)
        correlation_id: Optional ID to correlate related events
        occurred_at: When the event occurred (defaults to now)
        defer_routing: If True, route via transaction.on_commit (default)
    
    Returns:
        UUID of the created EventLog entry
    
    Example:
        emit_event(
            name="deal.won",
            tenant_id=deal.tenant_id,
            actor={"type": "user", "id": str(user.id)},
            entity={"type": "deal", "id": str(deal.id)},
            payload={"amount": deal.amount, "currency": deal.currency}
        )
    """
    # Strict event contract validation: emitted payload must satisfy payload_schema.
    payload_norm = _normalize_payload(payload or {})
    # Best-effort enrichment for downstream UX (e.g., embed contact snapshot when contact_id is present).
    # Fail-open: emission should never break due to enrichment.
    try:
        payload_norm = _maybe_enrich_payload(name, tenant_id, payload_norm)
    except Exception:  # pragma: no cover
        pass
    try:
        schema = get_event_payload_schema(name)
    except KeyError as exc:
        raise ValueError(str(exc)) from exc
    try:
        Draft202012Validator(schema).validate(payload_norm)
    except JsonSchemaValidationError as exc:
        raise ValueError(
            f"Invalid payload for event '{name}': {exc.message}"
        ) from exc

    event = _create_event_log(
        name=name,
        tenant_id=tenant_id,
        actor=actor,
        entity=entity,
        payload=payload_norm,
        source=source,
        correlation_id=correlation_id,
        occurred_at=occurred_at,
    )
    
    if defer_routing:
        transaction.on_commit(lambda: _dispatch_to_router(event.id))
    else:
        _dispatch_to_router(event.id)
    
    return event.id


def emit_event_sync(
    name: str,
    tenant_id: UUID,
    *,
    actor: Optional[dict] = None,
    entity: Optional[dict] = None,
    payload: Optional[dict] = None,
    source: str = "api",
    correlation_id: Optional[UUID] = None,
    occurred_at: Optional[datetime] = None,
) -> tuple[UUID, list]:
    """
    Emit an event and route it synchronously.
    
    Unlike emit_event(), this routes immediately without using
    transaction.on_commit or Celery. Useful for testing or when
    immediate routing is required.
    
    Returns:
        Tuple of (event_id, list of flow execution results)
    """
    from .router import route_event
    
    event = _create_event_log(
        name=name,
        tenant_id=tenant_id,
        actor=actor,
        entity=entity,
        payload=payload,
        source=source,
        correlation_id=correlation_id,
        occurred_at=occurred_at,
    )
    
    results = route_event(event.id)
    return event.id, results
