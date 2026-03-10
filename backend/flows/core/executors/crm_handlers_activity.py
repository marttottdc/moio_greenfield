"""Flow CRM CRUD handlers for Activity and ActivitySuggestion."""

from __future__ import annotations

from typing import Any, Dict


def _get_tenant(ctx: dict):
    tenant_id = ctx.get("tenant_id")
    if not tenant_id:
        raise ValueError("Missing tenant_id in flow context")
    from central_hub.models import Tenant
    return Tenant.objects.get(id=tenant_id)


def _parse_dt(s: Any):
    if s is None:
        return None
    if hasattr(s, "isoformat"):
        return s
    from django.utils.dateparse import parse_datetime
    return parse_datetime(str(s)) if s else None


def handle_activity_operation(*, operation: str, data: dict, ctx: dict) -> dict:
    operation = str(operation or "").strip().lower()
    if operation != "create":
        raise ValueError(f"Unsupported operation '{operation}' for activity")

    tenant = _get_tenant(ctx)
    from crm.models import ActivityType, ActivityRecord, ActivitySourceChoices
    from crm.services.activity_service import create_activity

    type_key = (data.get("type_key") or "").strip()
    if not type_key:
        raise ValueError("type_key is required")

    activity_type = ActivityType.objects.filter(tenant=tenant, key=type_key).first()
    title = (data.get("title") or "").strip() or f"Activity: {type_key}"
    kind = data.get("kind") or "task"
    status = data.get("status") or "planned"
    source = data.get("source") or "system"
    if source not in ("manual", "system", "suggestion"):
        source = "system"

    contact = None
    if data.get("contact_id"):
        from crm.models import Contact
        contact = Contact.objects.filter(
            tenant=tenant,
            user_id=data.get("contact_id"),
        ).first()

    customer = None
    customer_id = data.get("customer_id") or data.get("client_id")
    if customer_id:
        from crm.models import Customer
        try:
            customer = Customer.objects.get(tenant=tenant, id=customer_id)
        except Exception:
            pass

    deal = None
    if data.get("deal_id"):
        from crm.models import Deal
        try:
            deal = Deal.objects.get(tenant=tenant, id=data.get("deal_id"))
        except Exception:
            pass

    record = create_activity(
        kind=kind,
        title=title,
        content=data.get("content") or {},
        tenant=tenant,
        user=None,
        source=source,
        activity_type=activity_type,
        status=status,
        scheduled_at=_parse_dt(data.get("scheduled_at")),
        contact=contact,
        customer=customer,
        deal=deal,
        reason=(data.get("reason") or "")[:200],
    )

    obj = {
        "activity_id": str(record.pk),
        "title": record.title,
        "type_key": type_key,
        "status": record.status,
    }
    return {"success": True, "id": str(record.pk), "object": obj}


def handle_activity_suggestion_operation(*, operation: str, data: dict, ctx: dict) -> dict:
    operation = str(operation or "").strip().lower()
    if operation != "create":
        raise ValueError(f"Unsupported operation '{operation}' for activity_suggestion")

    tenant = _get_tenant(ctx)
    from crm.models import ActivitySuggestion, ActivitySuggestionStatus

    type_key = (data.get("type_key") or "").strip()
    reason = (data.get("reason") or "").strip()
    created_by_source = (data.get("created_by_source") or "flow").strip()
    if not type_key or not reason:
        raise ValueError("type_key and reason are required")

    suggestion = ActivitySuggestion.objects.create(
        tenant=tenant,
        type_key=type_key,
        reason=reason[:200],
        confidence=data.get("confidence"),
        expires_at=_parse_dt(data.get("expires_at")),
        proposed_fields=data.get("proposed_fields") or {},
        target_contact_id=data.get("target_contact_id") or None,
        target_customer_id=data.get("target_customer_id")
        or data.get("target_client_id")
        or None,
        target_deal_id=data.get("target_deal_id") or None,
        status=ActivitySuggestionStatus.PENDING,
        created_by_source=created_by_source[:60],
    )

    obj = {
        "suggestion_id": str(suggestion.pk),
        "type_key": type_key,
        "reason": suggestion.reason,
        "status": suggestion.status,
    }
    return {"success": True, "id": str(suggestion.pk), "object": obj}


__all__ = ["handle_activity_operation", "handle_activity_suggestion_operation"]
