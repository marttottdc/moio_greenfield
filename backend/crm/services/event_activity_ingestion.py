"""
Event → ActivityRecord ingestion.

Creates system ActivityRecords from platform events (deals, tickets, orders,
chatbot sessions, contacts) so contact timelines show a complete audit.
Idempotent: re-running for the same event does not duplicate activities.
Skips crm.activity.* events to avoid loops.
"""
from __future__ import annotations

import logging
from typing import Any, Optional, Set
from uuid import UUID

from django.db.models import Q

from crm.models import (
    ActivityRecord,
    Contact,
    Deal,
    Ticket,
)
from crm.services.activity_service import create_activity

logger = logging.getLogger(__name__)

# Event names we ingest (all others are skipped except for loop check)
DEAL_EVENTS = {"deal.created", "deal.updated", "deal.stage_changed", "deal.won", "deal.lost"}
TICKET_EVENTS = {"ticket.created", "ticket.updated", "ticket.closed"}
CONTACT_EVENTS = {"contact.created", "contact.updated"}
ORDER_EVENTS = {"order.created", "order.paid"}
CHATBOT_SESSION_EVENTS = {"chatbot_session.created", "chatbot_session.inactivated"}

INGESTED_EVENTS = DEAL_EVENTS | TICKET_EVENTS | CONTACT_EVENTS | ORDER_EVENTS | CHATBOT_SESSION_EVENTS


def extract_contact_ids_from_payload(payload: dict) -> Set[str]:
    """Collect contact identifiers from event payload (flat and nested)."""
    ids: Set[str] = set()
    if not isinstance(payload, dict):
        return ids
    for key in ("contact_id", "creator_id", "assigned_id", "waiting_for_id"):
        val = payload.get(key)
        if val is not None and str(val).strip():
            ids.add(str(val).strip())
    contact = payload.get("contact")
    if isinstance(contact, dict) and contact.get("id"):
        ids.add(str(contact["id"]))
    if isinstance(contact, dict) and contact.get("contact_id"):
        ids.add(str(contact["contact_id"]))
    if isinstance(contact, dict) and contact.get("user_id"):
        ids.add(str(contact["user_id"]))
    return ids


def _resolve_tenant(tenant_id: UUID):
    from portal.models import Tenant
    return Tenant.objects.filter(tenant_code=tenant_id).first()


def _get_contact(tenant, contact_id: str) -> Optional[Contact]:
    if not tenant or not contact_id:
        return None
    return Contact.objects.filter(tenant=tenant).filter(
        Q(user_id=contact_id) | Q(pk=contact_id)
    ).first()


def _event_content(event, payload_trim: dict) -> dict:
    """Build content dict with event metadata for idempotency and display."""
    occurred = event.occurred_at
    return {
        "event": {
            "event_id": str(event.id),
            "name": event.name,
            "occurred_at": occurred.isoformat() if occurred else None,
            "payload": payload_trim,
        }
    }


def _title_for_event(event_name: str, payload: dict, **extra) -> str:
    """Deterministic title per event type."""
    if event_name in DEAL_EVENTS:
        title = payload.get("title") or payload.get("deal_name") or payload.get("name") or "Deal"
        if event_name == "deal.created":
            return f"Deal created: {title}"
        if event_name == "deal.updated":
            return f"Deal updated: {title}"
        if event_name == "deal.stage_changed":
            return f"Deal stage changed: {title}"
        if event_name == "deal.won":
            return f"Deal won: {title}"
        if event_name == "deal.lost":
            return f"Deal lost: {title}"
        return f"Deal: {title}"
    if event_name in TICKET_EVENTS:
        service = payload.get("service") or "ticket"
        type_ = payload.get("type") or "incident"
        if event_name == "ticket.created":
            return f"Ticket created: {service}/{type_}"
        if event_name == "ticket.updated":
            return f"Ticket updated: {service}/{type_}"
        if event_name == "ticket.closed":
            return "Ticket closed"
        return f"Ticket: {service}/{type_}"
    if event_name == "contact.created":
        return "Contact created"
    if event_name == "contact.updated":
        return "Contact updated"
    if event_name == "order.created":
        return f"Order created: {payload.get('order_id', 'order')}"
    if event_name == "order.paid":
        return f"Order paid: {payload.get('order_id', 'order')}"
    if event_name == "chatbot_session.created":
        return "Chatbot session started"
    if event_name == "chatbot_session.inactivated":
        return "Chatbot session ended"
    return f"Event: {event_name}"


def _already_created(tenant, contact_id: str, event_id: UUID) -> bool:
    """Idempotency: activity for this event + contact already exists."""
    return ActivityRecord.objects.filter(
        tenant=tenant,
        contact_id=contact_id,
        content__event__event_id=str(event_id),
        source="system",
    ).exists()


def create_activities_from_event(event_id: UUID) -> int:
    """
    Create system ActivityRecords for an EventLog entry when it relates to contacts.
    Returns the number of activities created.
    Skips crm.activity.* to avoid loops. Idempotent per (event_id, contact).
    """
    from flows.models import EventLog

    try:
        event = EventLog.objects.get(id=event_id)
    except EventLog.DoesNotExist:
        logger.warning("EventLog not found: %s", event_id)
        return 0

    if event.name.startswith("crm.activity."):
        return 0

    if event.name not in INGESTED_EVENTS:
        return 0

    tenant = _resolve_tenant(event.tenant_id)
    if not tenant:
        logger.warning("Tenant not found for tenant_id=%s", event.tenant_id)
        return 0

    payload = event.payload or {}
    occurred_at = event.occurred_at
    payload_trim = {k: v for k, v in payload.items() if k not in ("deal", "contact", "ticket", "creator", "assigned", "waiting_for")}
    content = _event_content(event, payload_trim)
    title = _title_for_event(event.name, payload)

    created_count = 0

    if event.name in DEAL_EVENTS:
        deal_id = payload.get("deal_id")
        if not deal_id:
            return 0
        try:
            deal = Deal.objects.filter(tenant=tenant, id=deal_id).select_related("contact").first()
        except Exception:
            deal = None
        if not deal:
            return 0
        contact = deal.contact
        if not contact:
            return 0
        if _already_created(tenant, contact.user_id, event.id):
            return 0
        try:
            activity = create_activity(
                kind="other",
                title=title,
                content=content,
                tenant=tenant,
                user=None,
                source="system",
                visibility="internal",
                contact=contact,
                deal=deal,
            )
            activity.occurred_at = occurred_at
            activity.save(update_fields=["occurred_at"])
            created_count += 1
        except Exception as e:
            logger.exception("Failed to create activity for deal event %s: %s", event_id, e)
        return created_count

    if event.name in TICKET_EVENTS:
        ticket_id = payload.get("ticket_id")
        if not ticket_id:
            return 0
        try:
            ticket = Ticket.objects.filter(tenant=tenant, id=ticket_id).select_related(
                "creator", "assigned", "waiting_for"
            ).first()
        except Exception:
            ticket = None
        if not ticket:
            return 0
        contacts = []
        for c in (ticket.creator, ticket.assigned, ticket.waiting_for):
            if c and c not in contacts:
                contacts.append(c)
        for contact in contacts:
            if _already_created(tenant, contact.user_id, event.id):
                continue
            try:
                activity = create_activity(
                    kind="other",
                    title=title,
                    content=content,
                    tenant=tenant,
                    user=None,
                    source="system",
                    visibility="internal",
                    contact=contact,
                    ticket=ticket,
                )
                activity.occurred_at = occurred_at
                activity.save(update_fields=["occurred_at"])
                created_count += 1
            except Exception as e:
                logger.exception("Failed to create activity for ticket event %s contact %s: %s", event_id, contact.user_id, e)
        return created_count

    if event.name in CONTACT_EVENTS:
        contact_id = payload.get("contact_id")
        if not contact_id:
            return 0
        contact = _get_contact(tenant, contact_id)
        if not contact:
            return 0
        if _already_created(tenant, contact.user_id, event.id):
            return 0
        try:
            activity = create_activity(
                kind="other",
                title=title,
                content=content,
                tenant=tenant,
                user=None,
                source="system",
                visibility="internal",
                contact=contact,
            )
            activity.occurred_at = occurred_at
            activity.save(update_fields=["occurred_at"])
            created_count += 1
        except Exception as e:
            logger.exception("Failed to create activity for contact event %s: %s", event_id, e)
        return created_count

    if event.name in ORDER_EVENTS:
        contact_id = payload.get("contact_id")
        if not contact_id:
            return 0
        contact = _get_contact(tenant, contact_id)
        if not contact:
            return 0
        if _already_created(tenant, contact.user_id, event.id):
            return 0
        try:
            activity = create_activity(
                kind="other",
                title=title,
                content=content,
                tenant=tenant,
                user=None,
                source="system",
                visibility="internal",
                contact=contact,
            )
            activity.occurred_at = occurred_at
            activity.save(update_fields=["occurred_at"])
            created_count += 1
        except Exception as e:
            logger.exception("Failed to create activity for order event %s: %s", event_id, e)
        return created_count

    if event.name in CHATBOT_SESSION_EVENTS:
        contact_id = payload.get("contact_id")
        if not contact_id:
            session_id = payload.get("session_id")
            if session_id:
                try:
                    from chatbot.models import ChatbotSession
                    session = ChatbotSession.objects.filter(tenant=tenant).filter(
                        Q(session=session_id) | Q(id=session_id)
                    ).select_related("contact").first()
                    if session and session.contact_id:
                        contact_id = str(session.contact_id)
                except Exception:
                    pass
        if not contact_id:
            return 0
        contact = _get_contact(tenant, contact_id)
        if not contact:
            return 0
        if _already_created(tenant, contact.user_id, event.id):
            return 0
        try:
            activity = create_activity(
                kind="other",
                title=title,
                content=content,
                tenant=tenant,
                user=None,
                source="system",
                visibility="internal",
                contact=contact,
            )
            activity.occurred_at = occurred_at
            activity.save(update_fields=["occurred_at"])
            created_count += 1
        except Exception as e:
            logger.exception("Failed to create activity for chatbot_session event %s: %s", event_id, e)
        return created_count

    return created_count
