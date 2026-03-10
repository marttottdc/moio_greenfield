from __future__ import annotations

from typing import Any, Dict


def _get_tenant(ctx: dict):
    tenant_id = ctx.get("tenant_id")
    if not tenant_id:
        raise ValueError("Missing tenant_id in flow context")
    from central_hub.models import Tenant
    return Tenant.objects.get(id=tenant_id)


def _serialize_contact(contact) -> dict:
    # Contact may use user_id as PK; keep both stable.
    return {
        "contact_id": str(getattr(contact, "user_id", None) or getattr(contact, "id", "")),
        "fullname": getattr(contact, "fullname", "") or "",
        "phone": getattr(contact, "phone", "") or "",
        "email": getattr(contact, "email", "") or "",
        "whatsapp_name": getattr(contact, "whatsapp_name", "") or "",
        "company": getattr(contact, "company", "") or "",
    }


def handle_contact_operation(*, operation: str, data: dict, ctx: dict) -> dict:
    operation = str(operation or "").strip().lower()
    tenant = _get_tenant(ctx)

    from crm.models import Contact
    from crm.services.contact_service import ContactService

    if operation == "create":
        contact, _ = ContactService.create_contact(
            tenant=tenant,
            fullname=data.get("fullname") or "",
            email=data.get("email") or "",
            phone=data.get("phone") or "",
            whatsapp_name=data.get("whatsapp_name") or "",
            source=data.get("source") or "flow",
            ctype_name=data.get("contact_type_name"),
            ctype_pk=data.get("contact_type_id"),
        )
        if not contact:
            raise ValueError("Failed to create contact")
        obj = _serialize_contact(contact)
        return {"success": True, "id": obj["contact_id"], "object": obj}

    if operation == "get":
        contact_id = data.get("contact_id")
        contact = Contact.objects.filter(user_id=contact_id, tenant=tenant).first()
        if not contact:
            raise ValueError("Contact not found")
        obj = _serialize_contact(contact)
        return {"success": True, "id": obj["contact_id"], "object": obj}

    if operation == "update":
        contact_id = data.get("contact_id")
        contact = Contact.objects.filter(user_id=contact_id, tenant=tenant).first()
        if not contact:
            raise ValueError("Contact not found")
        # Partial update of allowed fields
        for field in ("fullname", "phone", "email", "whatsapp_name", "company"):
            if field in data and data.get(field) is not None:
                setattr(contact, field, data.get(field) or "")
        contact.save()
        obj = _serialize_contact(contact)
        return {"success": True, "id": obj["contact_id"], "object": obj}

    if operation == "delete":
        contact_id = data.get("contact_id")
        deleted = Contact.objects.filter(user_id=contact_id, tenant=tenant).delete()
        if not deleted or deleted[0] == 0:
            raise ValueError("Contact not found")
        return {"success": True, "id": str(contact_id)}

    if operation in {"list", "filter"}:
        qs = Contact.objects.filter(tenant=tenant)
        if operation == "list":
            q = (data.get("q") or "").strip()
            if q:
                # Best-effort: leverage manager search if available, else fallback.
                try:
                    qs = Contact.objects.search(q, tenant=tenant)
                except Exception:
                    qs = qs.filter(fullname__icontains=q)
        else:
            filters = data.get("filters") or {}
            if filters.get("phone"):
                qs = qs.filter(phone=str(filters.get("phone")))
            if filters.get("email"):
                qs = qs.filter(email__iexact=str(filters.get("email")))
            if filters.get("fullname_contains"):
                qs = qs.filter(fullname__icontains=str(filters.get("fullname_contains")))

        total = qs.count()
        limit = int(data.get("limit") or 50)
        offset = int(data.get("offset") or 0)
        items = [_serialize_contact(c) for c in qs.order_by("-created")[offset:offset + limit]]
        return {"success": True, "items": items, "total": total}

    raise ValueError(f"Unsupported operation '{operation}' for contact")


__all__ = ["handle_contact_operation"]

