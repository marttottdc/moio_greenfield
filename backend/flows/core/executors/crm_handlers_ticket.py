from __future__ import annotations


def _get_tenant(ctx: dict):
    tenant_id = ctx.get("tenant_id")
    if not tenant_id:
        raise ValueError("Missing tenant_id in flow context")
    from portal.models import Tenant
    return Tenant.objects.get(id=tenant_id)


def _serialize_ticket(ticket) -> dict:
    return {
        "ticket_id": str(getattr(ticket, "id", "")),
        "contact_id": str(getattr(ticket, "creator_id", "") or ""),
        "service": getattr(ticket, "service", "") or "",
        "description": getattr(ticket, "description", "") or "",
        "status": getattr(ticket, "status", "") or "",
        "type": getattr(ticket, "type", "") or "",
    }


def handle_ticket_operation(*, operation: str, data: dict, ctx: dict) -> dict:
    operation = str(operation or "").strip().lower()
    tenant = _get_tenant(ctx)

    from crm.models import Ticket, Contact
    from crm.services.ticket_service import TicketService

    if operation == "create":
        contact_id = data.get("contact_id")
        contact = Contact.objects.filter(user_id=contact_id, tenant=tenant).first()
        if not contact:
            raise ValueError("Contact not found for ticket creation")
        ticket, _ = TicketService.create_ticket(
            tenant=tenant,
            contact=contact,
            description=data.get("description") or "",
            service=data.get("service") or "general",
        )
        if not ticket:
            raise ValueError("Failed to create ticket")
        obj = _serialize_ticket(ticket)
        return {"success": True, "id": obj["ticket_id"], "object": obj}

    if operation == "get":
        ticket_id = data.get("ticket_id")
        ticket = TicketService.get_ticket_by_id(ticket_id, tenant)
        if not ticket:
            raise ValueError("Ticket not found")
        obj = _serialize_ticket(ticket)
        return {"success": True, "id": obj["ticket_id"], "object": obj}

    if operation == "update":
        ticket_id = data.get("ticket_id")
        ticket = TicketService.get_ticket_by_id(ticket_id, tenant)
        if not ticket:
            raise ValueError("Ticket not found")
        for field in ("status", "service", "description"):
            if field in data and data.get(field) is not None:
                setattr(ticket, field, data.get(field) or "")
        ticket.save()
        obj = _serialize_ticket(ticket)
        return {"success": True, "id": obj["ticket_id"], "object": obj}

    if operation == "delete":
        ticket_id = data.get("ticket_id")
        deleted = Ticket.objects.filter(id=ticket_id, tenant=tenant).delete()
        if not deleted or deleted[0] == 0:
            raise ValueError("Ticket not found")
        return {"success": True, "id": str(ticket_id)}

    if operation in {"list", "filter"}:
        qs = Ticket.objects.filter(tenant=tenant)
        if operation == "list":
            status = (data.get("status") or "").strip()
            if status:
                qs = qs.filter(status=status)
        else:
            filters = data.get("filters") or {}
            if filters.get("contact_id"):
                qs = qs.filter(creator_id=str(filters.get("contact_id")))
            if filters.get("status"):
                qs = qs.filter(status=str(filters.get("status")))
            if filters.get("service"):
                qs = qs.filter(service=str(filters.get("service")))

        total = qs.count()
        limit = int(data.get("limit") or 50)
        offset = int(data.get("offset") or 0)
        items = [_serialize_ticket(t) for t in qs.order_by("-created")[offset:offset + limit]]
        return {"success": True, "items": items, "total": total}

    raise ValueError(f"Unsupported operation '{operation}' for ticket")


__all__ = ["handle_ticket_operation"]

