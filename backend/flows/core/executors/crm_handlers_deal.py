from __future__ import annotations


def _get_tenant(ctx: dict):
    tenant_id = ctx.get("tenant_id")
    if not tenant_id:
        raise ValueError("Missing tenant_id in flow context")
    from portal.models import Tenant
    return Tenant.objects.get(id=tenant_id)


def _serialize_deal(deal) -> dict:
    return {
        "deal_id": str(getattr(deal, "id", "")),
        "title": getattr(deal, "title", "") or "",
        "description": getattr(deal, "description", "") or "",
        "value": float(getattr(deal, "value", 0) or 0),
        "currency": getattr(deal, "currency", "") or "",
        "status": getattr(deal, "status", "") or "",
        "priority": getattr(deal, "priority", "") or "",
        "contact_id": str(getattr(deal, "contact_id", "") or ""),
        "pipeline_id": str(getattr(deal, "pipeline_id", "") or ""),
        "stage_id": str(getattr(deal, "stage_id", "") or ""),
    }


def handle_deal_operation(*, operation: str, data: dict, ctx: dict) -> dict:
    operation = str(operation or "").strip().lower()
    tenant = _get_tenant(ctx)

    from crm.models import Deal

    if operation == "create":
        deal = Deal.objects.create(
            tenant=tenant,
            title=data.get("title") or "",
            description=data.get("description") or "",
            value=data.get("value") or 0,
            currency=data.get("currency") or "USD",
            status=data.get("status") or getattr(Deal, "status", "") or "",
            priority=data.get("priority") or getattr(Deal, "priority", "") or "",
            contact_id=data.get("contact_id") or None,
            pipeline_id=data.get("pipeline_id") or None,
            stage_id=data.get("stage_id") or None,
        )
        obj = _serialize_deal(deal)
        return {"success": True, "id": obj["deal_id"], "object": obj}

    if operation == "get":
        deal_id = data.get("deal_id")
        deal = Deal.objects.filter(id=deal_id, tenant=tenant).first()
        if not deal:
            raise ValueError("Deal not found")
        obj = _serialize_deal(deal)
        return {"success": True, "id": obj["deal_id"], "object": obj}

    if operation == "update":
        deal_id = data.get("deal_id")
        deal = Deal.objects.filter(id=deal_id, tenant=tenant).first()
        if not deal:
            raise ValueError("Deal not found")
        for field in ("title", "description", "value", "currency", "status", "priority"):
            if field in data and data.get(field) is not None:
                setattr(deal, field, data.get(field))
        for fk_field in ("contact_id", "pipeline_id", "stage_id"):
            if fk_field in data:
                setattr(deal, fk_field, data.get(fk_field) or None)
        deal.save()
        obj = _serialize_deal(deal)
        return {"success": True, "id": obj["deal_id"], "object": obj}

    if operation == "delete":
        deal_id = data.get("deal_id")
        deleted = Deal.objects.filter(id=deal_id, tenant=tenant).delete()
        if not deleted or deleted[0] == 0:
            raise ValueError("Deal not found")
        return {"success": True, "id": str(deal_id)}

    if operation in {"list", "filter"}:
        qs = Deal.objects.filter(tenant=tenant)
        if operation == "list":
            status = (data.get("status") or "").strip()
            if status:
                qs = qs.filter(status=status)
        else:
            filters = data.get("filters") or {}
            for key in ("status", "priority", "contact_id", "pipeline_id", "stage_id"):
                if filters.get(key):
                    qs = qs.filter(**{key: filters.get(key)})

        total = qs.count()
        limit = int(data.get("limit") or 50)
        offset = int(data.get("offset") or 0)
        items = [_serialize_deal(d) for d in qs.order_by("-created_at")[offset:offset + limit]]
        return {"success": True, "items": items, "total": total}

    raise ValueError(f"Unsupported operation '{operation}' for deal")


__all__ = ["handle_deal_operation"]

