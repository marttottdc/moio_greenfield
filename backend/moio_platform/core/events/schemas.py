"""Canonical event payload schemas (code-defined).

This is the single source of truth for event payload contracts.

We intentionally do NOT rely on mutating EventDefinition rows at runtime/migrations
to enforce schema changes. Database rows may exist for discovery/UI, but
validation uses these canonical schemas.
"""

from __future__ import annotations

from typing import Any, Dict


# ---------------------------------------------------------------------------
# Snapshot schemas (best-effort, internal)
#
# These are embedded into some event payloads for convenience.
# We keep `additionalProperties: True` so snapshots can evolve without breaking
# strict event validation, but we explicitly declare common fields so flows can:
# - reliably navigate them (contract/path resolver)
# - get better builder UX (hints/autocomplete where supported)
# ---------------------------------------------------------------------------

CONTACT_SNAPSHOT_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "id": {"type": ["string", "null"]},
        "contact_id": {"type": ["string", "null"]},
        "user_id": {"type": ["string", "null"]},
        "fullname": {"type": ["string", "null"]},
        "display_name": {"type": ["string", "null"]},
        "whatsapp_name": {"type": ["string", "null"]},
        "email": {"type": ["string", "null"]},
        "phone": {"type": ["string", "null"]},
        "company": {"type": ["string", "null"]},
        "type_id": {"type": ["string", "null"]},
        "type_name": {"type": ["string", "null"]},
        "created_at": {"type": ["string", "null"], "format": "date-time"},
        "updated_at": {"type": ["string", "null"], "format": "date-time"},
        "is_deleted": {"type": ["boolean", "null"]},
    },
    "additionalProperties": True,
}

# Contact snapshot or null (deals can have no contact)
CONTACT_SNAPSHOT_OR_NULL: Dict[str, Any] = {
    "oneOf": [CONTACT_SNAPSHOT_SCHEMA, {"type": "null"}],
}

DEAL_SNAPSHOT_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "id": {"type": ["string", "null"]},
        "deal_id": {"type": ["string", "null"]},
        "title": {"type": ["string", "null"]},
        "description": {"type": ["string", "null"]},
        "value": {"type": ["number", "null"]},
        "currency": {"type": ["string", "null"]},
        "status": {"type": ["string", "null"]},
        "pipeline_id": {"type": ["string", "null"]},
        "pipeline_name": {"type": ["string", "null"]},
        "stage_id": {"type": ["string", "null"]},
        "stage_name": {"type": ["string", "null"]},
        "contact_id": {"type": ["string", "null"]},
        # Some snapshots include embedded contact (optional when deal has no contact)
        "contact": CONTACT_SNAPSHOT_OR_NULL,
    },
    "additionalProperties": True,
}


# NOTE: Keep this in sync with the platform event contract.
EVENT_PAYLOAD_SCHEMAS: Dict[str, Dict[str, Any]] = {
    # CRM
    "crm.activity.created": {
        "type": "object",
        "properties": {
            "activity_id": {"type": "string"},
            "activity_type": {"type": ["string", "null"]},
            "status": {"type": ["string", "null"]},
            "kind": {"type": ["string", "null"]},
            "title": {"type": ["string", "null"]},
            "content": {"type": ["object", "null"]},
        },
        "required": ["activity_id"],
        "additionalProperties": True,
    },
    "crm.activity.updated": {
        "type": "object",
        "properties": {
            "activity_id": {"type": "string"},
            "activity_type": {"type": ["string", "null"]},
            "status": {"type": ["string", "null"]},
        },
        "required": ["activity_id"],
        "additionalProperties": True,
    },
    "crm.activity.status_changed": {
        "type": "object",
        "properties": {
            "activity_id": {"type": "string"},
            "old_status": {"type": "string"},
            "new_status": {"type": "string"},
        },
        "required": ["activity_id", "old_status", "new_status"],
        "additionalProperties": True,
    },
    "deal.created": {
        "type": "object",
        "properties": {
            "deal_id": {"type": "string"},
            # Canonical: Deal.title
            "title": {"type": "string"},
            # Backwards-compatible aliases (older flows/event defs used these)
            "name": {"type": ["string", "null"]},
            "deal_name": {"type": ["string", "null"]},
            "description": {"type": ["string", "null"]},
            "value": {"type": "number"},
            # Backwards-compatible alias (older defs used deal_value)
            "deal_value": {"type": ["number", "null"]},
            "currency": {"type": ["string", "null"]},
            "stage_id": {"type": ["string", "null"]},
            "stage_name": {"type": ["string", "null"]},
            "contact_id": {"type": ["string", "null"]},
            "pipeline_id": {"type": ["string", "null"]},
            "pipeline_name": {"type": ["string", "null"]},
            "status": {"type": ["string", "null"]},
            # Nested snapshots (full-internal, best-effort)
            # Important: must allow nested properties so flows can read
            # `input.body.deal.contact.email`, `input.body.contact.email`, etc.
            # contact can be None when deal has no contact
            "deal": {**DEAL_SNAPSHOT_SCHEMA, "type": ["object", "null"]},
            "contact": CONTACT_SNAPSHOT_OR_NULL,
        },
        "required": ["deal_id", "title"],
        "additionalProperties": True,
    },
    "deal.updated": {
        "type": "object",
        "properties": {
            "deal_id": {"type": "string"},
            "changed_fields": {"type": "array", "items": {"type": "string"}},
            "previous_values": {"type": "object"},
            "new_values": {"type": "object"},
            # Optional snapshots (full-internal, best-effort)
            "deal": {**DEAL_SNAPSHOT_SCHEMA, "type": ["object", "null"]},
            "contact": CONTACT_SNAPSHOT_OR_NULL,
        },
        "required": ["deal_id", "changed_fields"],
        "additionalProperties": True,
    },
    "deal.stage_changed": {
        "type": "object",
        "properties": {
            "deal_id": {"type": "string"},
            "title": {"type": "string"},
            # Backwards-compatible aliases
            "name": {"type": ["string", "null"]},
            "deal_name": {"type": ["string", "null"]},
            "description": {"type": ["string", "null"]},
            "contact_id": {"type": ["string", "null"]},
            "from_stage_id": {"type": ["string", "null"]},
            "from_stage_name": {"type": ["string", "null"]},
            "to_stage_id": {"type": ["string", "null"]},
            "to_stage_name": {"type": ["string", "null"]},
            "pipeline_id": {"type": ["string", "null"]},
            "pipeline_name": {"type": ["string", "null"]},
            # Canonical numeric amount + alias
            "value": {"type": ["number", "null"]},
            "deal_value": {"type": ["number", "null"]},
            "currency": {"type": ["string", "null"]},
            "deal": {**DEAL_SNAPSHOT_SCHEMA, "type": ["object", "null"]},
            "contact": CONTACT_SNAPSHOT_OR_NULL,
        },
        "required": ["deal_id", "title", "to_stage_id"],
        "additionalProperties": True,
    },
    "deal.won": {
        "type": "object",
        "properties": {
            "deal_id": {"type": "string"},
            "title": {"type": "string"},
            # Backwards-compatible aliases
            "name": {"type": ["string", "null"]},
            "deal_name": {"type": ["string", "null"]},
            "value": {"type": "number"},
            "deal_value": {"type": ["number", "null"]},
            "currency": {"type": ["string", "null"]},
            "won_by": {"type": ["string", "null"]},
            "contact_id": {"type": ["string", "null"]},
            "deal": {**DEAL_SNAPSHOT_SCHEMA, "type": ["object", "null"]},
            "contact": CONTACT_SNAPSHOT_OR_NULL,
        },
        "required": ["deal_id", "title"],
        "additionalProperties": True,
    },
    "deal.lost": {
        "type": "object",
        "properties": {
            "deal_id": {"type": "string"},
            "title": {"type": "string"},
            # Backwards-compatible aliases
            "name": {"type": ["string", "null"]},
            "deal_name": {"type": ["string", "null"]},
            "value": {"type": ["number", "null"]},
            "deal_value": {"type": ["number", "null"]},
            "currency": {"type": ["string", "null"]},
            "lost_reason": {"type": ["string", "null"]},
            "competitor": {"type": ["string", "null"]},
            "deal": {**DEAL_SNAPSHOT_SCHEMA, "type": ["object", "null"]},
            "contact": CONTACT_SNAPSHOT_OR_NULL,
        },
        "required": ["deal_id", "title"],
        "additionalProperties": True,
    },
    "contact.created": {
        "type": "object",
        "properties": {
            "contact_id": {"type": "string"},
            "fullname": {"type": ["string", "null"]},
            "display_name": {"type": ["string", "null"]},
            "whatsapp_name": {"type": ["string", "null"]},
            "email": {"type": ["string", "null"]},
            "phone": {"type": ["string", "null"]},
            "company": {"type": ["string", "null"]},
            "source": {"type": ["string", "null"]},
            "type_id": {"type": ["string", "null"]},
            "type_name": {"type": ["string", "null"]},
            "created_at": {"type": ["string", "null"], "format": "date-time"},
            "updated_at": {"type": ["string", "null"], "format": "date-time"},
            "is_deleted": {"type": "boolean"},
        },
        "required": ["contact_id"],
        "additionalProperties": True,
    },
    "contact.updated": {
        "type": "object",
        "properties": {
            "contact_id": {"type": "string"},
            "changed_fields": {"type": "array", "items": {"type": "string"}},
            "previous_values": {"type": "object"},
            "new_values": {"type": "object"},
        },
        "required": ["contact_id", "changed_fields"],
        "additionalProperties": True,
    },
    # Tickets (align to crm.models.Ticket)
    "ticket.created": {
        "type": "object",
        "properties": {
            "ticket_id": {"type": "string"},
            "type": {"type": ["string", "null"]},
            "service": {"type": ["string", "null"]},
            "description": {"type": ["string", "null"]},
            "status": {"type": ["string", "null"]},
            "created_at": {"type": ["string", "null"], "format": "date-time"},
            "last_updated_at": {"type": ["string", "null"], "format": "date-time"},

            "creator_id": {"type": ["string", "null"]},
            "creator_name": {"type": ["string", "null"]},
            "assigned_id": {"type": ["string", "null"]},
            "assigned_name": {"type": ["string", "null"]},
            "waiting_for_id": {"type": ["string", "null"]},
            "waiting_for_name": {"type": ["string", "null"]},
            "waiting_since": {"type": ["string", "null"], "format": "date-time"},

            "origin_type": {"type": ["string", "null"]},
            "origin_ref": {"type": ["string", "null"]},
            "origin_session_id": {"type": ["string", "null"]},

            # Nested snapshots (full-internal, best-effort)
            "ticket": {"type": ["object", "null"]},
            "creator": {"type": ["object", "null"]},
            "assigned": {"type": ["object", "null"]},
            "waiting_for": {"type": ["object", "null"]},
        },
        "required": ["ticket_id"],
        "additionalProperties": True,
    },
    "ticket.updated": {
        "type": "object",
        "properties": {
            "ticket_id": {"type": "string"},
            "type": {"type": ["string", "null"]},
            "service": {"type": ["string", "null"]},
            "description": {"type": ["string", "null"]},
            "status": {"type": ["string", "null"]},
            "changed_fields": {"type": "array", "items": {"type": "string"}},
            "updated_at": {"type": ["string", "null"], "format": "date-time"},
            "previous_values": {"type": "object"},
            "new_values": {"type": "object"},

            "ticket": {"type": ["object", "null"]},
            "creator": {"type": ["object", "null"]},
            "assigned": {"type": ["object", "null"]},
            "waiting_for": {"type": ["object", "null"]},
        },
        "required": ["ticket_id", "changed_fields"],
        "additionalProperties": True,
    },
    "ticket.closed": {
        "type": "object",
        "properties": {
            "ticket_id": {"type": "string"},
            "status": {"type": ["string", "null"]},
            "closed_at": {"type": ["string", "null"], "format": "date-time"},
            "duration_minutes": {"type": ["integer", "null"]},
        },
        "required": ["ticket_id"],
        "additionalProperties": True,
    },

    # Chatbot
    "message.received": {
        "type": "object",
        "properties": {
            "message_id": {"type": "string"},
            "contact_id": {"type": "string"},
            "channel": {"type": "string"},
            "content": {"type": "string"},
            "content_type": {"type": "string"},
            "conversation_id": {"type": "string"},
            "contact": {"type": ["object", "null"]},
        },
        "required": ["message_id", "contact_id", "channel", "content"],
        "additionalProperties": True,
    },
    "message.sent": {
        "type": "object",
        "properties": {
            "message_id": {"type": "string"},
            "contact_id": {"type": "string"},
            "channel": {"type": "string"},
            "content": {"type": "string"},
            "message_type": {"type": "string"},
            "template_id": {"type": "string"},
            "sent_at": {"type": "string", "format": "date-time"},
            "sent_by": {"type": "string"},
            "contact": {"type": ["object", "null"]},
        },
        "required": ["message_id", "contact_id", "channel"],
        "additionalProperties": True,
    },

    # Communications (ChatbotSession lifecycle)
    "communications.session_started": {
        "type": "object",
        "properties": {
            "session_id": {"type": "string"},
            "contact_id": {"type": ["string", "null"]},
            "channel": {"type": ["string", "null"]},
            "started_at": {"type": ["string", "null"], "format": "date-time"},
            "active": {"type": ["boolean", "null"]},
            "context": {"type": "object"},
            "contact": {"type": ["object", "null"]},
            "session": {"type": ["object", "null"]},
        },
        "required": ["session_id"],
        "additionalProperties": True,
    },
    "communications.session_ended": {
        "type": "object",
        "properties": {
            "session_id": {"type": "string"},
            "contact_id": {"type": ["string", "null"]},
            "channel": {"type": ["string", "null"]},
            "started_at": {"type": ["string", "null"], "format": "date-time"},
            "ended_at": {"type": ["string", "null"], "format": "date-time"},
            "active": {"type": ["boolean", "null"]},
            "context": {"type": "object"},
            "final_summary": {"type": ["string", "null"]},
            "csat": {"type": ["integer", "null"]},
            "messages_count": {"type": ["integer", "null"]},
            "messages": {"type": ["array", "null"]},
            "contact": {"type": ["object", "null"]},
            "session": {"type": ["object", "null"]},
        },
        "required": ["session_id"],
        "additionalProperties": True,
    },

    # Flows (execution completion)
    "flow.execution_completed": {
        "type": "object",
        "properties": {
            "flow_id": {"type": "string"},
            "execution_id": {"type": "string"},
            "status": {"type": ["string", "null"]},
            "trigger_source": {"type": ["string", "null"]},
            "execution_mode": {"type": ["string", "null"]},
            "sandbox": {"type": ["boolean", "null"]},
            "started_at": {"type": ["string", "null"], "format": "date-time"},
            "completed_at": {"type": ["string", "null"], "format": "date-time"},
            "duration_ms": {"type": ["integer", "null"]},
            "version_id": {"type": ["string", "null"]},
            "trace_id": {"type": ["string", "null"]},
            "input": {"type": "object"},
            "output": {"type": "object"},
            "error": {"type": "object"},
            "execution": {"type": ["object", "null"]},
        },
        "required": ["flow_id", "execution_id"],
        "additionalProperties": True,
    },

    # Campaigns
    "campaign.started": {
        "type": "object",
        "properties": {
            "campaign_id": {"type": "string"},
            "name": {"type": "string"},
            "channel": {"type": ["string", "null"]},
            "kind": {"type": ["string", "null"]},
            "status": {"type": ["string", "null"]},
            "audience_id": {"type": ["string", "null"]},
            "audience_name": {"type": ["string", "null"]},
            "audience_size": {"type": ["integer", "null"]},
            "job_ids": {"type": "array", "items": {"type": "string"}},
            "started_at": {"type": "string", "format": "date-time"},
        },
        "required": ["campaign_id", "name"],
        "additionalProperties": True,
    },
    "campaign.completed": {
        "type": "object",
        "properties": {
            "campaign_id": {"type": "string"},
            "name": {"type": "string"},
            "reason": {"type": ["string", "null"]},
            "sent": {"type": ["integer", "null"]},
            "opened": {"type": ["integer", "null"]},
            "responded": {"type": ["integer", "null"]},
            "completed_at": {"type": "string", "format": "date-time"},
        },
        "required": ["campaign_id"],
        "additionalProperties": True,
    },

    # Chatbot sessions
    "chatbot_session.created": {
        "type": "object",
        "properties": {
            "session_id": {"type": "string"},
            "contact_id": {"type": ["string", "null"]},
            "contact_name": {"type": ["string", "null"]},
            "channel": {"type": ["string", "null"]},
            "started_at": {"type": ["string", "null"], "format": "date-time"},
            "active": {"type": "boolean"},
        },
        "required": ["session_id"],
        "additionalProperties": True,
    },
    "chatbot_session.inactivated": {
        "type": "object",
        "properties": {
            "session_id": {"type": "string"},
            "contact_id": {"type": ["string", "null"]},
            "contact_name": {"type": ["string", "null"]},
            "channel": {"type": ["string", "null"]},
            "ended_at": {"type": ["string", "null"], "format": "date-time"},
            "active": {"type": "boolean"},
        },
        "required": ["session_id"],
        "additionalProperties": True,
    },

    # Integrations - Email
    "email.received": {
        "type": "object",
        "properties": {
            "provider": {"type": ["string", "null"]},
            "account_id": {"type": ["string", "null"]},
            "message": {
                "type": "object",
                "properties": {
                    "id": {"type": ["string", "null"]},
                    "thread_id": {"type": ["string", "null"]},
                    "from": {"type": ["string", "null"]},
                    "to": {"type": "array", "items": {"type": "string"}},
                    "subject": {"type": ["string", "null"]},
                    "text": {"type": ["string", "null"]},
                    "html": {"type": ["string", "null"]},
                    "attachments": {"type": "array", "items": {"type": "object"}},
                    "received_at": {"type": ["string", "null"], "format": "date-time"},
                },
                "required": ["id"],
                "additionalProperties": True,
            },
        },
        "required": ["provider", "account_id", "message"],
        "additionalProperties": True,
    },

    # Integrations - Calendar
    "calendar.event_received": {
        "type": "object",
        "properties": {
            "provider": {"type": ["string", "null"]},
            "account_id": {"type": ["string", "null"]},
            "event": {
                "type": "object",
                "properties": {
                    "id": {"type": ["string", "null"]},
                    "title": {"type": ["string", "null"]},
                    "start": {"type": ["string", "null"], "format": "date-time"},
                    "end": {"type": ["string", "null"], "format": "date-time"},
                    "attendees": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["id"],
                "additionalProperties": True,
            },
        },
        "required": ["provider", "account_id", "event"],
        "additionalProperties": True,
    },

    # Commerce
    "order.created": {
        "type": "object",
        "properties": {
            "order_id": {"type": "string"},
            "contact_id": {"type": "string"},
            "total": {"type": "number"},
            "currency": {"type": "string"},
            "items_count": {"type": "integer"},
            "payment_status": {"type": "string"},
        },
        "required": ["order_id", "total"],
        "additionalProperties": True,
    },
    "order.paid": {
        "type": "object",
        "properties": {
            "order_id": {"type": "string"},
            "total": {"type": "number"},
            "currency": {"type": "string"},
            "paid_at": {"type": "string", "format": "date-time"},
            "payment_method": {"type": "string"},
        },
        "required": ["order_id", "total"],
        "additionalProperties": True,
    },
}


def get_event_payload_schema(event_name: str) -> Dict[str, Any]:
    try:
        schema = EVENT_PAYLOAD_SCHEMAS[str(event_name)]
    except KeyError as exc:
        raise KeyError(f"No canonical payload schema registered for event '{event_name}'") from exc
    return schema

