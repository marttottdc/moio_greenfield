"""
Ticket domain events module.

Combines event emission for flow triggers with WebSocket notifications
for real-time UI updates. All ticket mutations should use these functions
to ensure both audit logging and real-time synchronization.
"""

import logging
from uuid import UUID
from typing import Optional, Dict, Any
from django.db import transaction
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer

from moio_platform.core.events import emit_event
from moio_platform.core.events.snapshots import snapshot_contact, snapshot_ticket
from crm.models import Ticket

logger = logging.getLogger(__name__)


def _send_ticket_websocket(
    tenant_id: UUID,
    event_type: str,
    payload: Dict[str, Any],
    ticket_id: Optional[UUID] = None,
) -> None:
    """
    Send a WebSocket message to connected ticket subscribers.
    
    Sends to both:
    - tickets_{tenant_id} (all ticket updates for tenant)
    - ticket_{tenant_id}_{ticket_id} (specific ticket updates)
    """
    try:
        channel_layer = get_channel_layer()
        if not channel_layer:
            logger.warning("Channel layer not available for WebSocket notifications")
            return
        
        message = {
            'type': event_type,
            'payload': payload,
        }
        
        # Send to tenant-wide ticket group
        group_name = f"tickets_{tenant_id}"
        async_to_sync(channel_layer.group_send)(group_name, message)
        
        # Also send to specific ticket group if ticket_id provided
        if ticket_id:
            specific_group = f"ticket_{tenant_id}_{ticket_id}"
            async_to_sync(channel_layer.group_send)(specific_group, message)
            
    except Exception as e:
        logger.error(f"Failed to send WebSocket notification: {e}", exc_info=True)


def emit_ticket_created(
    ticket: Ticket,
    actor_id: UUID,
) -> None:
    """
    Emit ticket.created event and send WebSocket notification.
    
    Should be called after ticket is created in the database.
    Call this within the same transaction that creates the ticket.
    """
    tenant_id = ticket.tenant_id
    ticket_id = ticket.id
    tenant_code = ticket.tenant.tenant_code
    
    # Build payload aligned to crm.models.Ticket (and include human-friendly names).
    payload = {
        "ticket_id": str(ticket_id),
        "type": getattr(ticket, "type", None),
        "service": getattr(ticket, "service", None),
        "description": getattr(ticket, "description", None),
        "status": getattr(ticket, "status", None),
        "created_at": ticket.created.isoformat() if getattr(ticket, "created", None) else None,
        "last_updated_at": ticket.last_updated.isoformat() if getattr(ticket, "last_updated", None) else None,
        "creator_id": str(ticket.creator_id) if getattr(ticket, "creator_id", None) else None,
        "creator_name": ticket.creator.fullname if getattr(ticket, "creator", None) else None,
        "assigned_id": str(ticket.assigned_id) if getattr(ticket, "assigned_id", None) else None,
        "assigned_name": ticket.assigned.fullname if getattr(ticket, "assigned", None) else None,
        "waiting_for_id": str(ticket.waiting_for_id) if getattr(ticket, "waiting_for_id", None) else None,
        "waiting_for_name": ticket.waiting_for.fullname if getattr(ticket, "waiting_for", None) else None,
        "waiting_since": ticket.waiting_since.isoformat() if getattr(ticket, "waiting_since", None) else None,
        "origin_type": getattr(ticket, "origin_type", None),
        "origin_ref": getattr(ticket, "origin_ref", None),
        "origin_session_id": str(ticket.origin_session_id) if getattr(ticket, "origin_session_id", None) else None,
        # Actionable nested snapshot + contact snapshots
        "ticket": snapshot_ticket(ticket, include_contacts=True),
        "creator": snapshot_contact(ticket.creator) if getattr(ticket, "creator", None) else None,
        "assigned": snapshot_contact(ticket.assigned) if getattr(ticket, "assigned", None) else None,
        "waiting_for": snapshot_contact(ticket.waiting_for) if getattr(ticket, "waiting_for", None) else None,
    }
    
    # Emit event for flow triggers
    def emit_on_commit():
        event_id = emit_event(
            name="ticket.created",
            tenant_id=tenant_code,
            actor={"type": "user", "id": str(actor_id)},
            entity={"type": "ticket", "id": str(ticket_id)},
            payload=payload,
            source="api",
        )
        # Create activities immediately from the emitted event so tickets
        # show up in timeline even if async workers are delayed/unavailable.
        try:
            from crm.services.event_activity_ingestion import create_activities_from_event
            create_activities_from_event(event_id)
        except Exception as ingest_err:
            logger.warning("Immediate ticket activity ingestion failed for %s: %s", event_id, ingest_err)
        
        # Send WebSocket notification
        _send_ticket_websocket(
            tenant_id=tenant_id,
            event_type="ticket_created",
            payload=payload,
            ticket_id=ticket_id,
        )
    
    transaction.on_commit(emit_on_commit)


def emit_ticket_updated(
    ticket: Ticket,
    actor_id: UUID,
    changed_fields: list,
) -> None:
    """
    Emit ticket.updated event and send WebSocket notification.
    
    Args:
        ticket: The updated ticket instance
        actor_id: UUID of user who made the change
        changed_fields: List of field names that were changed
    """
    tenant_id = ticket.tenant_id
    ticket_id = ticket.id
    tenant_code = ticket.tenant.tenant_code
    
    payload = {
        "ticket_id": str(ticket_id),
        "type": getattr(ticket, "type", None),
        "service": getattr(ticket, "service", None),
        "description": getattr(ticket, "description", None),
        "status": getattr(ticket, "status", None),
        "changed_fields": changed_fields,
        "updated_at": ticket.last_updated.isoformat() if getattr(ticket, "last_updated", None) else None,
        "previous_values": {},
        "new_values": {},
        "ticket": snapshot_ticket(ticket, include_contacts=True),
        "creator": snapshot_contact(ticket.creator) if getattr(ticket, "creator", None) else None,
        "assigned": snapshot_contact(ticket.assigned) if getattr(ticket, "assigned", None) else None,
        "waiting_for": snapshot_contact(ticket.waiting_for) if getattr(ticket, "waiting_for", None) else None,
    }
    
    def emit_on_commit():
        event_id = emit_event(
            name="ticket.updated",
            tenant_id=tenant_code,
            actor={"type": "user", "id": str(actor_id)},
            entity={"type": "ticket", "id": str(ticket_id)},
            payload=payload,
            source="api",
        )
        # Keep activities in sync without waiting for async routing.
        try:
            from crm.services.event_activity_ingestion import create_activities_from_event
            create_activities_from_event(event_id)
        except Exception as ingest_err:
            logger.warning("Immediate ticket activity ingestion failed for %s: %s", event_id, ingest_err)
        
        _send_ticket_websocket(
            tenant_id=tenant_id,
            event_type="ticket_updated",
            payload=payload,
            ticket_id=ticket_id,
        )
    
    transaction.on_commit(emit_on_commit)


def emit_ticket_closed(
    ticket: Ticket,
    actor_id: UUID,
) -> None:
    """
    Emit ticket.closed event and send WebSocket notification.
    
    Should be called when ticket status changes to 'C' (closed).
    """
    tenant_id = ticket.tenant_id
    ticket_id = ticket.id
    tenant_code = ticket.tenant.tenant_code
    
    closed_at = ticket.closed or ticket.last_updated
    duration_minutes = None
    if getattr(ticket, "created", None) and closed_at:
        duration_minutes = int((closed_at - ticket.created).total_seconds() // 60)
    payload = {
        "ticket_id": str(ticket_id),
        "status": getattr(ticket, "status", None),
        "closed_at": closed_at.isoformat() if closed_at else None,
        "duration_minutes": duration_minutes,
        "ticket": snapshot_ticket(ticket, include_contacts=True),
        "creator": snapshot_contact(ticket.creator) if getattr(ticket, "creator", None) else None,
        "assigned": snapshot_contact(ticket.assigned) if getattr(ticket, "assigned", None) else None,
        "waiting_for": snapshot_contact(ticket.waiting_for) if getattr(ticket, "waiting_for", None) else None,
    }
    
    def emit_on_commit():
        event_id = emit_event(
            name="ticket.closed",
            tenant_id=tenant_code,
            actor={"type": "user", "id": str(actor_id)},
            entity={"type": "ticket", "id": str(ticket_id)},
            payload=payload,
            source="api",
        )
        # Keep activities in sync without waiting for async routing.
        try:
            from crm.services.event_activity_ingestion import create_activities_from_event
            create_activities_from_event(event_id)
        except Exception as ingest_err:
            logger.warning("Immediate ticket activity ingestion failed for %s: %s", event_id, ingest_err)
        
        _send_ticket_websocket(
            tenant_id=tenant_id,
            event_type="ticket_closed",
            payload=payload,
            ticket_id=ticket_id,
        )
    
    transaction.on_commit(emit_on_commit)
