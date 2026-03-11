from __future__ import annotations

from typing import Any, Dict, Optional

from django.db import connection, transaction
from django.db.models import Q
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.response import Response

from crm.api.mixins import PaginationMixin, ProtectedAPIView, _error
from crm.models import ActivityCaptureEntry, CaptureEntryLink, CaptureStatus
from crm.services.activity_capture_service import (
    build_proposed_activity_from_classification,
    classify_entry_via_openai,
    create_capture_entry,
    apply_capture_entry_to_activities,
)
from crm.tasks import classify_capture_entry, apply_capture_entry


def _serialize_capture_entry(entry: ActivityCaptureEntry, isoformat) -> Dict[str, Any]:
    return {
        "id": str(entry.id),
        "anchor_model": entry.anchor_model,
        "anchor_id": entry.anchor_id,
        "actor_id": str(entry.actor_id) if entry.actor_id else None,
        "raw_text": entry.raw_text,
        "raw_source": entry.raw_source,
        "channel_hint": entry.channel_hint,
        "visibility": entry.visibility,
        "status": entry.status,
        "llm_model": entry.llm_model,
        "prompt_version": entry.prompt_version,
        "classification": entry.classification,
        "suggested_activities": entry.suggested_activities or [],
        "summary": entry.summary,
        "confidence": entry.confidence,
        "needs_review": entry.needs_review,
        "review_reasons": entry.review_reasons or [],
        "final": entry.final,
        "applied_refs": entry.applied_refs,
        "idempotency_key": entry.idempotency_key,
        "created_at": isoformat(entry.created_at),
        "updated_at": isoformat(entry.updated_at),
    }


class _CaptureSerializerMixin:
    def _serialize(self, entry: ActivityCaptureEntry) -> Dict[str, Any]:
        return _serialize_capture_entry(entry, self._isoformat)


@method_decorator(csrf_exempt, name="dispatch")
@extend_schema(tags=["capture"])
class CaptureEntriesView(_CaptureSerializerMixin, PaginationMixin, ProtectedAPIView):
    ITEMS_KEY = "entries"

    def _base_queryset(self, request):
        tenant = self._get_tenant_or_none(request)
        if tenant is None:
            return ActivityCaptureEntry.objects.none()
        return ActivityCaptureEntry.objects.filter(tenant=tenant).select_related("actor", "tenant")

    def get(self, request):
        qs = self._base_queryset(request)

        status_filter = (request.query_params.get("status") or "").strip()
        if status_filter:
            qs = qs.filter(status=status_filter)

        anchor_model = (request.query_params.get("anchor_model") or "").strip()
        anchor_id = (request.query_params.get("anchor_id") or "").strip()
        if anchor_model and anchor_id:
            qs = qs.filter(anchor_model=anchor_model, anchor_id=anchor_id)

        qs = qs.order_by("-created_at")
        return Response(self._paginate(qs, request, self._serialize, "entries"))

    def post(self, request):
        tenant = self._get_tenant_or_none(request)
        if tenant is None:
            return _error("tenant_required", "User must belong to a tenant", status.HTTP_400_BAD_REQUEST)

        payload = request.data or {}
        raw_text = (payload.get("raw_text") or "").strip()
        anchor_model = payload.get("anchor_model") or payload.get("anchor") or ""
        anchor_id = payload.get("anchor_id") or payload.get("anchorId") or ""

        raw_source = payload.get("raw_source") or "manual_text"
        channel_hint = payload.get("channel_hint")
        visibility = payload.get("visibility")
        idempotency_key = payload.get("idempotency_key")

        try:
            entry, created = create_capture_entry(
                raw_text=raw_text,
                anchor_model=str(anchor_model),
                anchor_id=str(anchor_id),
                actor=request.user,
                raw_source=str(raw_source),
                channel_hint=channel_hint,
                visibility=visibility,
                idempotency_key=idempotency_key,
            )
        except ValueError as exc:
            code = str(exc) if str(exc) else "invalid_request"
            return _error(code, str(exc), status.HTTP_400_BAD_REQUEST)
        except Exception as exc:
            return _error("capture_failed", str(exc), status.HTTP_500_INTERNAL_SERVER_ERROR)

        # Schedule async classification after commit only for new entries.
        if created:
            transaction.on_commit(lambda: classify_capture_entry.delay(str(entry.id)))
        return Response(self._serialize(entry), status=status.HTTP_201_CREATED if created else status.HTTP_200_OK)


@method_decorator(csrf_exempt, name="dispatch")
@extend_schema(tags=["capture"])
class CaptureEntryDetailView(_CaptureSerializerMixin, PaginationMixin, ProtectedAPIView):
    def _get_entry(self, request, entry_id) -> Optional[ActivityCaptureEntry]:
        tenant = self._get_tenant_or_none(request)
        if tenant is None:
            return None
        try:
            return ActivityCaptureEntry.objects.filter(tenant=tenant).select_related("actor", "tenant").get(id=entry_id)
        except ActivityCaptureEntry.DoesNotExist:
            return None

    def get(self, request, entry_id):
        entry = self._get_entry(request, entry_id)
        if not entry:
            return _error("not_found", "Capture entry not found", status.HTTP_404_NOT_FOUND)
        return Response(self._serialize(entry))


def _ensure_mutable(entry: ActivityCaptureEntry) -> None:
    if entry.status in {CaptureStatus.APPLIED, CaptureStatus.APPLYING}:
        raise ValueError(f"entry_not_mutable:{entry.status}")


@method_decorator(csrf_exempt, name="dispatch")
@extend_schema(tags=["capture"])
class CaptureEntryApproveView(_CaptureSerializerMixin, PaginationMixin, ProtectedAPIView):
    def post(self, request, entry_id):
        tenant = self._get_tenant_or_none(request)
        if tenant is None:
            return _error("tenant_required", "User must belong to a tenant", status.HTTP_400_BAD_REQUEST)

        try:
            entry = ActivityCaptureEntry.objects.get(tenant=tenant, id=entry_id)
        except ActivityCaptureEntry.DoesNotExist:
            return _error("not_found", "Capture entry not found", status.HTTP_404_NOT_FOUND)

        payload = request.data or {}
        final = payload.get("final")
        if final is not None and not isinstance(final, dict):
            return _error("invalid_request", "final must be an object", status.HTTP_400_BAD_REQUEST)

        try:
            with transaction.atomic():
                entry = ActivityCaptureEntry.objects.select_for_update().get(id=entry.id)
                _ensure_mutable(entry)
                entry.final = final or entry.classification or {}
                entry.needs_review = False
                entry.status = CaptureStatus.REVIEWED
                entry.save(update_fields=["final", "needs_review", "status", "updated_at"])
        except ValueError as exc:
            return _error("invalid_state", str(exc), status.HTTP_400_BAD_REQUEST)

        transaction.on_commit(lambda: apply_capture_entry.delay(str(entry.id)))
        return Response(self._serialize(entry), status=status.HTTP_200_OK)


@method_decorator(csrf_exempt, name="dispatch")
@extend_schema(tags=["capture"])
class CaptureEntryNoteOnlyView(_CaptureSerializerMixin, PaginationMixin, ProtectedAPIView):
    def post(self, request, entry_id):
        tenant = self._get_tenant_or_none(request)
        if tenant is None:
            return _error("tenant_required", "User must belong to a tenant", status.HTTP_400_BAD_REQUEST)

        try:
            with transaction.atomic():
                entry = ActivityCaptureEntry.objects.select_for_update().get(tenant=tenant, id=entry_id)
                _ensure_mutable(entry)
                # Force a note-only final output (no intents)
                summary = (entry.summary or "").strip() or "Note"
                entry.final = {"summary": summary, "suggested_activities": []}
                entry.needs_review = False
                entry.status = CaptureStatus.REVIEWED
                entry.save(update_fields=["final", "needs_review", "status", "updated_at"])
        except ActivityCaptureEntry.DoesNotExist:
            return _error("not_found", "Capture entry not found", status.HTTP_404_NOT_FOUND)
        except ValueError as exc:
            return _error("invalid_state", str(exc), status.HTTP_400_BAD_REQUEST)

        transaction.on_commit(lambda: apply_capture_entry.delay(str(entry.id)))
        return Response(self._serialize(entry), status=status.HTTP_200_OK)


@method_decorator(csrf_exempt, name="dispatch")
@extend_schema(tags=["capture"])
class CaptureEntryRejectView(_CaptureSerializerMixin, PaginationMixin, ProtectedAPIView):
    def post(self, request, entry_id):
        tenant = self._get_tenant_or_none(request)
        if tenant is None:
            return _error("tenant_required", "User must belong to a tenant", status.HTTP_400_BAD_REQUEST)

        reason = (request.data or {}).get("reason") or ""
        reason = str(reason)[:500]

        try:
            with transaction.atomic():
                entry = ActivityCaptureEntry.objects.select_for_update().get(tenant=tenant, id=entry_id)
                _ensure_mutable(entry)
                entry.final = {"rejected": True, "reason": reason}
                entry.needs_review = False
                entry.status = CaptureStatus.REVIEWED
                entry.save(update_fields=["final", "needs_review", "status", "updated_at"])
        except ActivityCaptureEntry.DoesNotExist:
            return _error("not_found", "Capture entry not found", status.HTTP_404_NOT_FOUND)
        except ValueError as exc:
            return _error("invalid_state", str(exc), status.HTTP_400_BAD_REQUEST)

        return Response(self._serialize(entry), status=status.HTTP_200_OK)


@method_decorator(csrf_exempt, name="dispatch")
@extend_schema(tags=["capture"])
class CaptureEntrySplitView(_CaptureSerializerMixin, PaginationMixin, ProtectedAPIView):
    """
    Split a capture entry into multiple new child entries.
    Request shape:
      { "parts": ["text1", "text2", ...] }
    """

    def post(self, request, entry_id):
        tenant = self._get_tenant_or_none(request)
        if tenant is None:
            return _error("tenant_required", "User must belong to a tenant", status.HTTP_400_BAD_REQUEST)

        payload = request.data or {}
        parts = payload.get("parts")
        if not isinstance(parts, list) or not parts:
            return _error("invalid_request", "parts must be a non-empty list", status.HTTP_400_BAD_REQUEST)

        try:
            with transaction.atomic():
                parent = ActivityCaptureEntry.objects.select_for_update().get(tenant=tenant, id=entry_id)
                _ensure_mutable(parent)
                children: list[ActivityCaptureEntry] = []
                for raw in parts:
                    text = (str(raw) or "").strip()
                    if not text:
                        continue
                    child, _ = create_capture_entry(
                        raw_text=text,
                        anchor_model=parent.anchor_model,
                        anchor_id=parent.anchor_id,
                        actor=request.user,
                        raw_source=parent.raw_source,
                        channel_hint=parent.channel_hint,
                        visibility=parent.visibility,
                        idempotency_key=None,
                    )
                    CaptureEntryLink.objects.create(
                        tenant=tenant,
                        entry=child,
                        ref_model="crm.activity_capture_entry",
                        ref_id=str(parent.id),
                    )
                    children.append(child)

                parent.final = {"split_into": [str(c.id) for c in children]}
                parent.needs_review = False
                parent.status = CaptureStatus.REVIEWED
                parent.save(update_fields=["final", "needs_review", "status", "updated_at"])
        except ActivityCaptureEntry.DoesNotExist:
            return _error("not_found", "Capture entry not found", status.HTTP_404_NOT_FOUND)
        except ValueError as exc:
            return _error("invalid_state", str(exc), status.HTTP_400_BAD_REQUEST)
        except Exception as exc:
            return _error("split_failed", str(exc), status.HTTP_500_INTERNAL_SERVER_ERROR)

        # Schedule classification for children after commit.
        for child in children:
            transaction.on_commit(lambda cid=str(child.id): classify_capture_entry.delay(cid))
        return Response(
            {"parent": self._serialize(parent), "children": [self._serialize(c) for c in children]},
            status=status.HTTP_200_OK,
        )


def _user_timezone_for_request(request) -> str:
    from crm.services.activity_capture_service import _user_timezone
    return _user_timezone(request.user)


@method_decorator(csrf_exempt, name="dispatch")
@extend_schema(tags=["capture"])
class CaptureClassifySyncView(_CaptureSerializerMixin, PaginationMixin, ProtectedAPIView):
    """
    Run classification synchronously and return a preview (proposed_activity) for user confirmation.
    Creates a capture entry, runs the LLM classify in-process, saves classification, and returns
    entry + proposed_activity. The form can show the preview and then call apply-sync to create
    the activity on the spot.
    """

    def post(self, request):
        tenant = self._get_tenant_or_none(request)
        if tenant is None:
            return _error("tenant_required", "User must belong to a tenant", status.HTTP_400_BAD_REQUEST)

        payload = request.data or {}
        raw_text = (payload.get("raw_text") or "").strip()
        anchor_model = payload.get("anchor_model") or payload.get("anchor") or ""
        anchor_id = payload.get("anchor_id") or payload.get("anchorId") or ""

        if not raw_text:
            return _error("invalid_request", "raw_text is required", status.HTTP_400_BAD_REQUEST)

        try:
            entry, _ = create_capture_entry(
                raw_text=raw_text,
                anchor_model=str(anchor_model),
                anchor_id=str(anchor_id),
                actor=request.user,
                raw_source=payload.get("raw_source") or "manual_text",
                channel_hint=payload.get("channel_hint"),
                visibility=payload.get("visibility"),
                idempotency_key=payload.get("idempotency_key"),
            )
        except ValueError as exc:
            return _error(str(exc) or "invalid_request", str(exc), status.HTTP_400_BAD_REQUEST)

        try:
            output = classify_entry_via_openai(entry=entry)
        except ValueError as exc:
            return _error("classification_failed", str(exc), status.HTTP_400_BAD_REQUEST)
        except Exception as exc:
            return _error("classification_failed", str(exc), status.HTTP_500_INTERNAL_SERVER_ERROR)

        # OpenAI call can take 10–30s; DB connection may go stale. Close to force a fresh one.
        connection.close()
        # Re-set tenant on the new connection (django-tenants: fresh conn may default to public).
        from django.conf import settings
        if getattr(settings, "DJANGO_TENANTS_ENABLED", False) and getattr(tenant, "schema_name", None):
            connection.set_tenant(tenant)

        classification_payload = output.model_dump()
        suggested = classification_payload.get("suggested_activities")
        suggested_list = suggested if isinstance(suggested, list) else []
        with transaction.atomic():
            entry = ActivityCaptureEntry.objects.select_for_update().get(id=entry.id)
            _ensure_mutable(entry)
            entry.raw_llm_response = classification_payload
            entry.classification = classification_payload
            entry.suggested_activities = suggested_list
            entry.summary = classification_payload.get("summary")
            entry.confidence = classification_payload.get("confidence")
            entry.needs_review = True  # Always require confirmation when using sync classify
            entry.review_reasons = classification_payload.get("review_reasons") or []
            entry.status = CaptureStatus.NEEDS_REVIEW
            entry.save(
                update_fields=[
                    "raw_llm_response",
                    "classification",
                    "suggested_activities",
                    "summary",
                    "confidence",
                    "needs_review",
                    "review_reasons",
                    "status",
                    "updated_at",
                ]
            )

        user_tz = _user_timezone_for_request(request)
        proposed = build_proposed_activity_from_classification(
            entry=entry,
            classification=classification_payload,
            user_tz=user_tz,
        )

        return Response(
            {
                "entry": self._serialize(entry),
                "classification": classification_payload,
                "suggested_activities": proposed.get("suggested_activities", proposed.get("proposed_activities", [])),
                "proposed_activity": proposed.get("proposed_activity"),
                "proposed_activities": proposed.get("proposed_activities", []),
            },
            status=status.HTTP_200_OK,
        )


@method_decorator(csrf_exempt, name="dispatch")
@extend_schema(tags=["capture"])
class CaptureEntryApplySyncView(_CaptureSerializerMixin, PaginationMixin, ProtectedAPIView):
    """
    Apply a capture entry synchronously (create activity on the spot) after user confirmation.
    Expects the entry to have been classified (e.g. via classify-sync). Sets final from
    classification and runs apply in-process, then returns the entry and applied_refs.
    """

    def post(self, request, entry_id):
        tenant = self._get_tenant_or_none(request)
        if tenant is None:
            return _error("tenant_required", "User must belong to a tenant", status.HTTP_400_BAD_REQUEST)

        try:
            entry = ActivityCaptureEntry.objects.select_related("tenant", "actor").get(tenant=tenant, id=entry_id)
        except ActivityCaptureEntry.DoesNotExist:
            return _error("not_found", "Capture entry not found", status.HTTP_404_NOT_FOUND)

        payload = request.data or {}
        final_override = payload.get("final")
        confirmed_activities = payload.get("confirmed_activities")
        deal_id_override = payload.get("deal_id")
        contact_id_override = (payload.get("contact_id") or "").strip() or None
        customer_id_override = (payload.get("customer_id") or "").strip() or None

        # Build final: use confirmed_activities (user edits) or final override or classification
        if isinstance(confirmed_activities, list) and confirmed_activities:
            base = dict(entry.classification or {})
            base["confirmed_activities"] = confirmed_activities
            final_to_use = base
        elif isinstance(final_override, dict):
            final_to_use = final_override
        else:
            final_to_use = entry.classification or {}

        is_append = entry.status == CaptureStatus.APPLIED
        try:
            with transaction.atomic():
                entry = ActivityCaptureEntry.objects.select_for_update().select_related("actor").get(id=entry.id)
                if not is_append:
                    _ensure_mutable(entry)
                entry.final = final_to_use
                entry.needs_review = False
                if not is_append:
                    entry.status = CaptureStatus.REVIEWED
                entry.save(update_fields=["final", "needs_review", "status", "updated_at"])
        except ValueError as exc:
            return _error("invalid_state", str(exc), status.HTTP_400_BAD_REQUEST)

        try:
            result = apply_capture_entry_to_activities(
                entry=entry,
                actor=request.user,
                deal_id_override=deal_id_override,
                contact_id_override=contact_id_override,
                customer_id_override=customer_id_override,
            )
        except ValueError as exc:
            return _error("apply_failed", str(exc), status.HTTP_400_BAD_REQUEST)
        except Exception as exc:
            return _error("apply_failed", str(exc), status.HTTP_500_INTERNAL_SERVER_ERROR)

        # Normalize to applied_refs: [{model, id}, ...] for API/timeline
        activity_ids = result.get("activity_record_ids") or []
        deal_ids = result.get("deal_ids") or []
        new_refs = [
            *[{"model": "crm.activity", "id": aid} for aid in activity_ids],
            *[{"model": "crm.deal", "id": did} for did in deal_ids],
        ]

        with transaction.atomic():
            entry = ActivityCaptureEntry.objects.select_for_update().get(id=entry.id)
            if is_append and entry.applied_refs:
                existing = list(entry.applied_refs) if isinstance(entry.applied_refs, list) else []
                seen = {f"{r.get('model')}:{r.get('id')}" for r in existing if isinstance(r, dict)}
                for r in new_refs:
                    key = f"{r.get('model')}:{r.get('id')}"
                    if key not in seen:
                        seen.add(key)
                        existing.append(r)
                applied_refs = existing
            else:
                applied_refs = new_refs
            entry.applied_refs = applied_refs
            entry.status = CaptureStatus.APPLIED
            entry.save(update_fields=["applied_refs", "status", "updated_at"])

        return Response(
            {
                "entry": self._serialize(entry),
                "applied_refs": applied_refs,
            },
            status=status.HTTP_200_OK,
        )

