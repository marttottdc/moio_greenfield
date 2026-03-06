from __future__ import annotations


def _get_tenant(ctx: dict):
    tenant_id = ctx.get("tenant_id")
    if not tenant_id:
        raise ValueError("Missing tenant_id in flow context")
    from portal.models import Tenant
    return Tenant.objects.get(id=tenant_id)


def _serialize_audience(aud) -> dict:
    return {
        "audience_id": str(getattr(aud, "id", "")),
        "name": getattr(aud, "name", "") or "",
        "description": getattr(aud, "description", "") or "",
        "kind": getattr(aud, "kind", "") or "",
        "size": int(getattr(aud, "size", 0) or 0),
        "is_draft": bool(getattr(aud, "is_draft", True)),
    }


def handle_audience_operation(*, operation: str, data: dict, ctx: dict) -> dict:
    operation = str(operation or "").strip().lower()
    tenant = _get_tenant(ctx)

    from campaigns.models import Audience

    if operation == "create":
        aud = Audience.objects.create(
            tenant=tenant,
            name=data.get("name") or "",
            description=data.get("description") or "",
            kind=data.get("kind") or "static",
            rules=data.get("rules"),
            is_draft=bool(data.get("is_draft", True)),
        )
        obj = _serialize_audience(aud)
        return {"success": True, "id": obj["audience_id"], "object": obj}

    if operation == "get":
        audience_id = data.get("audience_id")
        aud = Audience.objects.filter(id=audience_id, tenant=tenant).first()
        if not aud:
            raise ValueError("Audience not found")
        obj = _serialize_audience(aud)
        return {"success": True, "id": obj["audience_id"], "object": obj}

    if operation == "update":
        audience_id = data.get("audience_id")
        aud = Audience.objects.filter(id=audience_id, tenant=tenant).first()
        if not aud:
            raise ValueError("Audience not found")
        for field in ("name", "description", "kind", "rules", "is_draft"):
            if field in data:
                setattr(aud, field, data.get(field))
        aud.save()
        obj = _serialize_audience(aud)
        return {"success": True, "id": obj["audience_id"], "object": obj}

    if operation == "delete":
        audience_id = data.get("audience_id")
        deleted = Audience.objects.filter(id=audience_id, tenant=tenant).delete()
        if not deleted or deleted[0] == 0:
            raise ValueError("Audience not found")
        return {"success": True, "id": str(audience_id)}

    if operation in {"list", "filter"}:
        qs = Audience.objects.filter(tenant=tenant)
        if operation == "list":
            kind = (data.get("kind") or "").strip()
            if kind:
                qs = qs.filter(kind=kind)
        else:
            filters = data.get("filters") or {}
            if filters.get("kind"):
                qs = qs.filter(kind=str(filters.get("kind")))
            if "is_draft" in filters and filters.get("is_draft") is not None:
                qs = qs.filter(is_draft=bool(filters.get("is_draft")))
            if filters.get("name_contains"):
                qs = qs.filter(name__icontains=str(filters.get("name_contains")))

        total = qs.count()
        limit = int(data.get("limit") or 50)
        offset = int(data.get("offset") or 0)
        items = [_serialize_audience(a) for a in qs.order_by("-created")[offset:offset + limit]]
        return {"success": True, "items": items, "total": total}

    raise ValueError(f"Unsupported operation '{operation}' for audience")


__all__ = ["handle_audience_operation"]

