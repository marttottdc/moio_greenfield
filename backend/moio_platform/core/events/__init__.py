"""
Event System for Moio Platform.

This module provides the event-driven architecture for flow triggering.
Events are facts that occurred in the system, emitted by business logic,
persisted for audit/replay, and routed to matching flows.

Usage:
    from moio_platform.core.events import emit_event

    emit_event(
        name="deal.won",
        tenant_id=deal.tenant_id,
        actor={"type": "user", "id": str(user.id)},
        entity={"type": "deal", "id": str(deal.id)},
        payload={"amount": deal.amount, "currency": deal.currency}
    )
"""

from .emitter import emit_event, emit_event_sync
from flows.models import EventDefinition, EventLog

__all__ = [
    "emit_event",
    "emit_event_sync",
    "EventDefinition",
    "EventLog",
]
