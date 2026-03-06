from __future__ import annotations

from datetime import datetime, timezone as dt_timezone
from typing import Any, Dict, Optional, Tuple

from django.db.models import Q
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.response import Response

from crm.api.activities.views import _serialize_activity_record
from crm.api.mixins import ProtectedAPIView, _error
from crm.models import ActivityCaptureEntry, ActivityRecord, CaptureAnchorModel
from portal.rbac import user_has_role


def _parse_cursor(raw: Optional[str]) -> Optional[Tuple[datetime, str]]:
    if not raw:
        return None
    value = str(raw).strip()
    if not value or "," not in value:
        return None
    dt_s, id_s = value.split(",", 1)
    dt_s = dt_s.strip()
    id_s = id_s.strip()
    try:
        if dt_s.endswith("Z"):
            dt_s = dt_s[:-1] + "+00:00"
        dt = datetime.fromisoformat(dt_s)
    except Exception:
        return None
    return dt, id_s


def _cursor_filter(*, dt: datetime, id_s: str) -> Q:
    # Descending order: items older than (dt, id)
    return Q(created_at__lt=dt) | (Q(created_at=dt) & Q(id__lt=id_s))


def _anchor_activity_filter(anchor_model: str, anchor_id: str) -> Q:
    if anchor_model == CaptureAnchorModel.DEAL:
        return Q(deal_id=anchor_id)
    if anchor_model == CaptureAnchorModel.CONTACT:
        return Q(contact_id=anchor_id)
    if anchor_model == CaptureAnchorModel.CUSTOMER:
        return Q(customer_id=anchor_id)
    return Q(pk__isnull=True)


def _visible_capture_q(user) -> Q:
    # public/internal always visible within tenant
    q = Q(visibility__in=["public", "internal"])
    # confidential visible to managers+ or the author
    if user_has_role(user, "manager") or getattr(user, "is_superuser", False):
        q |= Q(visibility="confidential")
    else:
        q |= Q(visibility="confidential", actor=user)
    # restricted visible if explicitly allowed, or superuser
    if getattr(user, "is_superuser", False):
        q |= Q(visibility="restricted")
    else:
        q |= Q(visibility="restricted", allowed_users=user) | Q(visibility="restricted", allowed_roles__in=user.groups.all())
    return q


def _visible_activity_q(user) -> Q:
    # Heuristic: reuse ActivityRecord.visibility but without explicit allow-lists.
    q = Q(visibility__in=["public", "internal"])
    if user_has_role(user, "manager") or getattr(user, "is_superuser", False):
        q |= Q(visibility="confidential")
    else:
        q |= Q(visibility="confidential", created_by=user) | Q(visibility="confidential", owner=user)

    if getattr(user, "is_superuser", False) or user_has_role(user, "tenant_admin"):
        q |= Q(visibility="restricted")
    else:
        q |= Q(visibility="restricted", created_by=user) | Q(visibility="restricted", owner=user)
    return q


def _serialize_capture(entry: ActivityCaptureEntry, isoformat) -> Dict[str, Any]:
    return {
        "type": "capture_entry",
        "id": str(entry.id),
        "created_at": isoformat(entry.created_at),
        "actor_id": str(entry.actor_id) if entry.actor_id else None,
        "anchor_model": entry.anchor_model,
        "anchor_id": entry.anchor_id,
        "status": entry.status,
        "summary": entry.summary,
        "confidence": entry.confidence,
        "needs_review": entry.needs_review,
        "visibility": entry.visibility,
        "raw_text": entry.raw_text,
        "applied_refs": entry.applied_refs,
    }


@method_decorator(csrf_exempt, name="dispatch")
@extend_schema(tags=["timeline"])
class TimelineView(ProtectedAPIView):
    """
    Unified timeline for an anchor.

    Params:
    - anchor_model: crm.deal | crm.contact | crm.customer (crm.account treated as crm.customer by capture APIs)
    - anchor_id
    - limit (default 50, max 100)
    - cursor: \"<iso_created_at>,<id>\" from previous response
    """

    def _isoformat(self, dt) -> Optional[str]:
        if not dt:
            return None
        if getattr(dt, "tzinfo", None) is None:
            # assume UTC when naive
            dt = dt.replace(tzinfo=dt_timezone.utc)
        return (
            dt.astimezone(dt_timezone.utc)
            .replace(microsecond=0)
            .isoformat()
            .replace("+00:00", "Z")
        )

    def get(self, request):
        tenant = getattr(request.user, "tenant", None)
        if tenant is None:
            return _error("tenant_required", "User must belong to a tenant", status.HTTP_400_BAD_REQUEST)

        anchor_model = (request.query_params.get("anchor_model") or "").strip().lower()
        anchor_id = (request.query_params.get("anchor_id") or "").strip()
        if not anchor_model or not anchor_id:
            return _error("invalid_request", "anchor_model and anchor_id are required", status.HTTP_400_BAD_REQUEST)

        if anchor_model == "crm.account":
            anchor_model = CaptureAnchorModel.CUSTOMER

        try:
            limit = int(request.query_params.get("limit") or "50")
        except ValueError:
            limit = 50
        limit = max(1, min(limit, 100))

        cursor = _parse_cursor(request.query_params.get("cursor"))

        capture_qs = (
            ActivityCaptureEntry.objects.filter(tenant=tenant, anchor_model=anchor_model, anchor_id=anchor_id)
            .filter(_visible_capture_q(request.user))
            .select_related("actor")
            .distinct()
        )
        activity_qs = (
            ActivityRecord.objects.filter(tenant=tenant)
            .filter(_anchor_activity_filter(anchor_model, anchor_id))
            .filter(_visible_activity_q(request.user))
            .select_related("type", "user", "owner", "created_by", "contact", "customer", "deal", "ticket")
        )

        if cursor:
            dt, id_s = cursor
            capture_qs = capture_qs.filter(_cursor_filter(dt=dt, id_s=id_s))
            activity_qs = activity_qs.filter(_cursor_filter(dt=dt, id_s=id_s))

        capture_items = list(capture_qs.order_by("-created_at", "-id")[: limit + 5])
        activity_items = list(activity_qs.order_by("-created_at", "-id")[: limit + 5])

        # Merge in python
        merged: list[dict] = []
        i = j = 0
        while len(merged) < limit and (i < len(capture_items) or j < len(activity_items)):
            next_capture = capture_items[i] if i < len(capture_items) else None
            next_activity = activity_items[j] if j < len(activity_items) else None

            take_capture = False
            if next_capture and not next_activity:
                take_capture = True
            elif next_capture and next_activity:
                if (next_capture.created_at, str(next_capture.id)) >= (next_activity.created_at, str(next_activity.id)):
                    take_capture = True

            if take_capture:
                merged.append(_serialize_capture(next_capture, self._isoformat))
                i += 1
            else:
                merged.append(
                    {
                        **_serialize_activity_record(next_activity, self._isoformat),
                        "type": "activity",
                    }
                )
                j += 1

        next_cursor = None
        if merged:
            last = merged[-1]
            next_cursor = f"{last['created_at']},{last['id']}"

        return Response({"items": merged, "next_cursor": next_cursor})

