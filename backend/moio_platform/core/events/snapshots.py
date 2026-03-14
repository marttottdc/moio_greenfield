from __future__ import annotations

from typing import Any, Optional


def snapshot_contact(contact) -> dict[str, Any]:
    """
    Full-internal (but stable) contact snapshot for event payloads.

    Uses `user_id` when available since that's the external identifier in many APIs.
    """
    contact_id = getattr(contact, "user_id", None) or getattr(contact, "pk", None)
    ctype = getattr(contact, "ctype", None)
    return {
        "id": str(contact_id) if contact_id is not None else None,
        "fullname": getattr(contact, "fullname", None),
        "display_name": getattr(contact, "display_name", None),
        "whatsapp_name": getattr(contact, "whatsapp_name", None),
        "email": getattr(contact, "email", None),
        "phone": getattr(contact, "phone", None) or getattr(contact, "mobile", None),
        "company": getattr(contact, "company", None),
        "source": getattr(contact, "source", None),
        "type_id": str(getattr(contact, "ctype_id", None)) if getattr(contact, "ctype_id", None) else None,
        "type_name": getattr(ctype, "name", None),
        # Often used by downstream automations
        "brief_facts": getattr(contact, "brief_facts", None) or {},
        "interactions_count": getattr(contact, "interactions_count", None),
        "last_contacted_at": getattr(contact, "last_contacted_at", None).isoformat() if getattr(contact, "last_contacted_at", None) else None,
        "created_at": getattr(contact, "created", None).isoformat() if getattr(contact, "created", None) else None,
        "updated_at": getattr(contact, "updated", None).isoformat() if getattr(contact, "updated", None) else None,
    }


def snapshot_deal(deal, *, include_contact: bool = True) -> dict[str, Any]:
    contact = getattr(deal, "contact", None)
    stage = getattr(deal, "stage", None)
    pipeline = getattr(deal, "pipeline", None)
    owner = getattr(deal, "owner", None)
    created_by = getattr(deal, "created_by", None)
    payload: dict[str, Any] = {
        "id": str(getattr(deal, "id", None)),
        "title": getattr(deal, "title", None),
        "description": getattr(deal, "description", None),
        "value": float(getattr(deal, "value", 0) or 0),
        "currency": getattr(deal, "currency", None),
        "probability": getattr(deal, "probability", None),
        "priority": getattr(deal, "priority", None),
        "status": getattr(deal, "status", None),
        "expected_close_date": getattr(deal, "expected_close_date", None).isoformat() if getattr(deal, "expected_close_date", None) else None,
        "actual_close_date": getattr(deal, "actual_close_date", None).isoformat() if getattr(deal, "actual_close_date", None) else None,
        "pipeline": {
            "id": str(getattr(deal, "pipeline_id", None)) if getattr(deal, "pipeline_id", None) else None,
            "name": getattr(pipeline, "name", None),
        },
        "stage": {
            "id": str(getattr(deal, "stage_id", None)) if getattr(deal, "stage_id", None) else None,
            "name": getattr(stage, "name", None),
        },
        "contact_id": str(getattr(deal, "contact_id", None)) if getattr(deal, "contact_id", None) else None,
        "owner": {
            "id": str(getattr(deal, "owner_id", None)) if getattr(deal, "owner_id", None) else None,
            "email": getattr(owner, "email", None),
            "name": (f"{getattr(owner, 'first_name', '')} {getattr(owner, 'last_name', '')}".strip() or None) if owner else None,
        },
        "created_by": {
            "id": str(getattr(deal, "created_by_id", None)) if getattr(deal, "created_by_id", None) else None,
            "email": getattr(created_by, "email", None),
        },
        "metadata": getattr(deal, "metadata", None) or {},
        "created_at": getattr(deal, "created_at", None).isoformat() if getattr(deal, "created_at", None) else None,
        "updated_at": getattr(deal, "updated_at", None).isoformat() if getattr(deal, "updated_at", None) else None,
    }
    if include_contact and contact is not None:
        payload["contact"] = snapshot_contact(contact)
    return payload


def snapshot_ticket(ticket, *, include_contacts: bool = True) -> dict[str, Any]:
    creator = getattr(ticket, "creator", None)
    assigned = getattr(ticket, "assigned", None)
    waiting_for = getattr(ticket, "waiting_for", None)
    payload: dict[str, Any] = {
        "id": str(getattr(ticket, "id", None)),
        "type": getattr(ticket, "type", None),
        "service": getattr(ticket, "service", None),
        "description": getattr(ticket, "description", None),
        "status": getattr(ticket, "status", None),
        "created_at": getattr(ticket, "created", None).isoformat() if getattr(ticket, "created", None) else None,
        "last_updated_at": getattr(ticket, "last_updated", None).isoformat() if getattr(ticket, "last_updated", None) else None,
        "target_at": getattr(ticket, "target", None).isoformat() if getattr(ticket, "target", None) else None,
        "closed_at": getattr(ticket, "closed", None).isoformat() if getattr(ticket, "closed", None) else None,
        "creator_id": str(getattr(ticket, "creator_id", None)) if getattr(ticket, "creator_id", None) else None,
        "assigned_id": str(getattr(ticket, "assigned_id", None)) if getattr(ticket, "assigned_id", None) else None,
        "waiting_for_id": str(getattr(ticket, "waiting_for_id", None)) if getattr(ticket, "waiting_for_id", None) else None,
        "waiting_since": getattr(ticket, "waiting_since", None).isoformat() if getattr(ticket, "waiting_since", None) else None,
        "origin": {
            "type": getattr(ticket, "origin_type", None),
            "ref": getattr(ticket, "origin_ref", None),
            "session_id": str(getattr(ticket, "origin_session_id", None)) if getattr(ticket, "origin_session_id", None) else None,
        },
    }
    if include_contacts:
        if creator is not None:
            payload["creator"] = snapshot_contact(creator)
        if assigned is not None:
            payload["assigned"] = snapshot_contact(assigned)
        if waiting_for is not None:
            payload["waiting_for"] = snapshot_contact(waiting_for)
    return payload


def snapshot_agent_session(session, *, messages_limit: int = 50) -> dict[str, Any]:
    """
    Full-internal agent session snapshot, bounded by `messages_limit` most recent thread messages.
    """
    contact = getattr(session, "contact", None)
    payload: dict[str, Any] = {
        "id": str(getattr(session, "pk", None)),
        "contact_id": str(getattr(session, "contact_id", None)) if getattr(session, "contact_id", None) else None,
        "channel": getattr(session, "channel", None),
        "active": getattr(session, "active", None),
        "busy": getattr(session, "busy", None),
        "human_mode": getattr(session, "human_mode", None),
        "start": getattr(session, "start", None).isoformat() if getattr(session, "start", None) else None,
        "end": getattr(session, "end", None).isoformat() if getattr(session, "end", None) else None,
        "last_interaction": getattr(session, "last_interaction", None).isoformat() if getattr(session, "last_interaction", None) else None,
        "started_by": getattr(session, "started_by", None),
        "context": getattr(session, "context", None) or {},
        "final_summary": getattr(session, "final_summary", None),
        "csat": getattr(session, "csat", None),
    }
    if contact is not None:
        payload["contact"] = snapshot_contact(contact)

    # Messages (bounded) from session.threads
    messages = []
    try:
        threads = getattr(session, "threads", None)
        if threads is not None:
            qs = threads.order_by("-created")[: max(0, int(messages_limit))]
            for msg in qs:
                messages.append(
                    {
                        "id": str(getattr(msg, "id", None)),
                        "role": getattr(msg, "role", None),
                        "author": getattr(msg, "author", None),
                        "content": getattr(msg, "content", None),
                        "created_at": getattr(msg, "created", None).isoformat() if getattr(msg, "created", None) else None,
                    }
                )
            total_messages = threads.count()
        else:
            total_messages = None
    except Exception:
        total_messages = None
    else:
        messages.reverse()

    payload["messages_count"] = total_messages
    payload["messages"] = messages
    payload["messages_truncated"] = (total_messages is not None and total_messages > len(messages))
    return payload


def snapshot_flow_execution(execution) -> dict[str, Any]:
    ctx = getattr(execution, "execution_context", None) or {}
    return {
        "id": str(getattr(execution, "id", None)),
        "flow_id": str(getattr(execution, "flow_id", None)) if getattr(execution, "flow_id", None) else None,
        "status": getattr(execution, "status", None),
        "trigger_source": getattr(execution, "trigger_source", None) or ctx.get("trigger_source"),
        "execution_mode": ctx.get("execution_mode"),
        "sandbox": ctx.get("sandbox"),
        "duration_ms": getattr(execution, "duration_ms", None),
        "started_at": getattr(execution, "started_at", None).isoformat() if getattr(execution, "started_at", None) else None,
        "completed_at": getattr(execution, "completed_at", None).isoformat() if getattr(execution, "completed_at", None) else None,
        "version_id": ctx.get("version_id"),
        "trace_id": ctx.get("trace_id"),
        "input": getattr(execution, "input_data", None) or {},
        "output": getattr(execution, "output_data", None) or {},
        "error": getattr(execution, "error_data", None) or {},
    }


