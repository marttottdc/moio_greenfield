from __future__ import annotations

from typing import Any, Dict, Optional

from django.core.exceptions import ObjectDoesNotExist
from django.db import transaction
from django.db.utils import ProgrammingError
from django.db.models import Q
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt
from drf_spectacular.utils import extend_schema, OpenApiParameter, OpenApiResponse
from drf_spectacular.types import OpenApiTypes
from jsonschema import ValidationError as JsonSchemaValidationError
from pydantic import ValidationError as PydanticValidationError
from rest_framework import status
from rest_framework.response import Response

from crm.models import (
    ActivityRecord,
    ActivitySuggestion,
    ActivitySuggestionStatus,
    ActivityType,
    ActivityKind,
)
from crm.api.activities.serializers import (
    ActivityCreateRequestSerializer,
    ActivityUpdateRequestSerializer,
    ActivityResponseSerializer,
    ActivityListResponseSerializer,
    ActivitySuggestionAcceptRequestSerializer,
    ActivitySuggestionListResponseSerializer,
)
from crm.api.mixins import PaginationMixin, ProtectedAPIView, _error
from crm.services.activity_service import _normalize_content, activity_manager
from crm.services.activity_suggestion_service import accept_suggestion, dismiss_suggestion
from tenancy.rbac import user_has_role
from tenancy.tenant_support import get_current_rls_debug_context, get_table_policies, tenant_rls_context

import logging

logger = logging.getLogger(__name__)


def _related_display(obj) -> Optional[str]:
    """Return display name for contact/customer (name only, not email)."""
    if not obj:
        return None
    # Contact: fullname, display_name, whatsapp_name, first+last (no email)
    # Customer: name, legal_name
    for attr in ("name", "nombre", "fullname", "display_name", "whatsapp_name", "legal_name"):
        val = getattr(obj, attr, None)
        if val and isinstance(val, str) and val.strip():
            return val.strip()
    # Fallback: first_name + last_name (Contact)
    fn = getattr(obj, "first_name", "") or ""
    ln = getattr(obj, "last_name", "") or ""
    combined = f"{fn} {ln}".strip()
    if combined:
        return combined
    return None


def _activity_author_display(user) -> str:
    """Return display name for activity author."""
    if not user:
        return "System"
    fn = getattr(user, "first_name", "") or ""
    ln = getattr(user, "last_name", "") or ""
    name = f"{fn} {ln}".strip()
    return name or getattr(user, "email", "") or getattr(user, "username", "") or "Unknown"


def _safe_related(instance, attr: str):
    try:
        return getattr(instance, attr)
    except ObjectDoesNotExist:
        return None


def _serialize_activity_record(activity: ActivityRecord, isoformat) -> Dict[str, Any]:
    author_user = activity.created_by or activity.user or activity.owner
    author = _activity_author_display(author_user)
    contact = _safe_related(activity, "contact") if activity.contact_id else None
    customer = _safe_related(activity, "customer") if activity.customer_id else None
    deal = _safe_related(activity, "deal") if activity.deal_id else None
    return {
        "id": str(activity.pk),
        "title": activity.title,
        "kind": activity.kind,
        "kind_label": activity.get_kind_display(),
        "type": activity.type.name if activity.type else None,
        "type_key": activity.type.key if activity.type else None,
        "content": activity.content,
        "source": activity.source,
        "visibility": activity.visibility,
        "visibility_label": activity.get_visibility_display(),
        "user_id": activity.user_id if activity.user else None,
        "author": author,
        "created_at": isoformat(activity.created_at),
        "status": activity.status,
        "status_label": activity.get_status_display(),
        "scheduled_at": isoformat(activity.scheduled_at),
        "occurred_at": isoformat(activity.occurred_at),
        "completed_at": isoformat(activity.completed_at),
        "duration_minutes": activity.duration_minutes,
        "owner_id": activity.owner_id,
        "created_by_id": activity.created_by_id,
        "contact_id": activity.contact_id,
        "contact_name": _related_display(contact) if contact else None,
        "customer_id": str(activity.customer_id) if activity.customer_id else None,
        "customer_name": _related_display(customer) if customer else None,
        "deal_id": str(activity.deal_id) if activity.deal_id else None,
        "deal_title": getattr(deal, "title", None) or getattr(deal, "name", None) if deal else None,
        "ticket_id": str(activity.ticket_id) if activity.ticket_id else None,
        "tags": activity.tags or [],
        "reason": activity.reason or "",
        "needs_confirmation": activity.needs_confirmation,
    }


class ActivitySerializerMixin:
    def _serialize_activity(self, activity: ActivityRecord) -> Dict[str, Any]:
        return _serialize_activity_record(activity, self._isoformat)


@method_decorator(csrf_exempt, name="dispatch")
@extend_schema(tags=["activities"])
class ActivitiesView(ActivitySerializerMixin, PaginationMixin, ProtectedAPIView):
    ITEMS_KEY = "activities"

    def _base_queryset(self, request):
        self._ensure_tenant_schema(request)
        tenant = self._get_tenant_or_none(request)
        if tenant is None:
            return ActivityRecord.objects.none()
        qs = ActivityRecord.objects.filter(tenant=tenant).select_related(
            "type", "user", "owner", "created_by", "contact", "customer", "deal", "ticket"
        )
        user = getattr(request, "user", None)
        if not user or not getattr(user, "is_authenticated", False):
            return qs.none()
        if getattr(user, "is_superuser", False) or user_has_role(user, "tenant_admin"):
            return qs
        if user_has_role(user, "manager"):
            supervised_ids = list(
                user.direct_reports.filter(tenant=tenant).values_list("pk", flat=True)
            )
            visible_user_ids = [user.pk] + supervised_ids
            return qs.filter(
                Q(user_id__in=visible_user_ids)
                | Q(owner_id__in=visible_user_ids)
                | Q(created_by_id__in=visible_user_ids)
            )
        visible = (
            Q(user=user) | Q(owner=user) | Q(created_by=user)
        )
        return qs.filter(visible)

    @extend_schema(
        summary="List activities",
        description="Paginated list of activities for the current tenant.",
        parameters=[
            OpenApiParameter("search", OpenApiTypes.STR, description="Search in title, source"),
            OpenApiParameter("kind", OpenApiTypes.STR, description="Filter by kind"),
            OpenApiParameter("status", OpenApiTypes.STR, description="Filter by status"),
            OpenApiParameter("contact_id", OpenApiTypes.UUID, description="Filter by contact"),
            OpenApiParameter("customer_id", OpenApiTypes.UUID, description="Filter by customer"),
            OpenApiParameter("deal_id", OpenApiTypes.UUID, description="Filter by deal"),
            OpenApiParameter("sort_by", OpenApiTypes.STR, description="Sort field", default="created_at"),
            OpenApiParameter("order", OpenApiTypes.STR, description="asc or desc", default="desc"),
            OpenApiParameter("page", OpenApiTypes.INT, description="Page number", default=1),
            OpenApiParameter("limit", OpenApiTypes.INT, description="Items per page", default=50),
        ],
        responses={200: ActivityListResponseSerializer},
    )
    def get(self, request):
        queryset = self._base_queryset(request)

        search = (request.query_params.get("search") or "").strip()
        if search:
            queryset = queryset.filter(
                Q(title__icontains=search) | Q(source__icontains=search)
            )

        kind_filter = request.query_params.get("kind")
        if kind_filter:
            queryset = queryset.filter(kind=kind_filter)

        status_filter = request.query_params.get("status")
        if status_filter:
            queryset = queryset.filter(status=status_filter)

        contact_id = request.query_params.get("contact_id")
        if contact_id:
            queryset = queryset.filter(contact_id=contact_id)

        customer_id = request.query_params.get("customer_id")
        if customer_id:
            queryset = queryset.filter(customer_id=customer_id)

        deal_id = request.query_params.get("deal_id")
        if deal_id:
            queryset = queryset.filter(deal_id=deal_id)

        owner_id = request.query_params.get("owner_id")
        if owner_id:
            queryset = queryset.filter(owner_id=owner_id)

        scheduled_from = request.query_params.get("scheduled_from")
        if scheduled_from:
            queryset = queryset.filter(scheduled_at__gte=scheduled_from)

        scheduled_to = request.query_params.get("scheduled_to")
        if scheduled_to:
            queryset = queryset.filter(scheduled_at__lte=scheduled_to)

        visibility_filter = request.query_params.get("visibility")
        if visibility_filter:
            queryset = queryset.filter(visibility=visibility_filter)

        sort_by = request.query_params.get("sort_by", "created_at")
        order = request.query_params.get("order", "desc")
        prefix = "-" if order == "desc" else ""

        allowed_sort_fields = {
            "created_at", "title", "kind", "visibility",
            "status", "scheduled_at", "occurred_at", "completed_at",
        }
        if sort_by not in allowed_sort_fields:
            sort_by = "created_at"

        queryset = queryset.order_by(f"{prefix}{sort_by}")
        return Response(self._paginate(queryset, request, self._serialize_activity, "activities"))

    @extend_schema(
        summary="Create activity",
        description="Create a new activity for the current tenant.",
        request=ActivityCreateRequestSerializer,
        responses={201: ActivityResponseSerializer},
    )
    def post(self, request):
        self._ensure_tenant_schema(request)
        tenant = self._get_tenant_or_none(request)
        if tenant is None:
            return _error("tenant_required", "User must belong to a tenant", status.HTTP_400_BAD_REQUEST)

        payload = request.data or {}
        title = (payload.get("title") or "").strip()
        kind = payload.get("kind", ActivityKind.NOTE)

        activity_type = None
        type_name = payload.get("type") or payload.get("type_key")
        if type_name:
            activity_type = ActivityType.objects.filter(tenant=tenant).filter(
                Q(key=type_name) | Q(name=type_name)
            ).first()

        source = payload.get("source")
        if source not in ("manual", "system", "suggestion"):
            source = "manual"
        try:
            content = _normalize_content(
                payload.get("content", {}),
                kind=kind,
                activity_type=activity_type,
            )
        except Exception as exc:
            return _error("invalid_request", str(exc), status.HTTP_400_BAD_REQUEST)

        # Use central activity manager for orchestration
        activity_data = {
            "kind": kind,
            "title": title or "No Title",
            "content": content,
            "source": source,
            "visibility": payload.get("visibility", "public"),
            "status": payload.get("status", "completed"),
            "scheduled_at": payload.get("scheduled_at"),
            "occurred_at": payload.get("occurred_at"),
            "completed_at": payload.get("completed_at"),
            "duration_minutes": payload.get("duration_minutes"),
            "contact_id": payload.get("contact_id"),
            "customer_id": payload.get("customer_id"),
            "deal_id": payload.get("deal_id"),
            "ticket_id": payload.get("ticket_id"),
            "tags": payload.get("tags", []),
            "reason": payload.get("reason", ""),
            "needs_confirmation": payload.get("needs_confirmation", False),
            "type_key": getattr(activity_type, 'key', None) if activity_type else None,
        }
        if "owner_id" in payload:
            activity_data["owner_id"] = payload.get("owner_id")
        if "created_by_id" in payload:
            activity_data["created_by_id"] = payload.get("created_by_id")

        try:
            with transaction.atomic(), tenant_rls_context(tenant):
                activity = activity_manager.create_activity(
                    activity_data,
                    tenant=tenant,
                    user=request.user if request.user.is_authenticated else None,
                    activity_type=activity_type
                )
                response_payload = self._serialize_activity(activity)
        except ProgrammingError as exc:
            if "row-level security policy" in str(exc).lower():
                logger.error(
                    "Activity create RLS violation tenant_id=%s tenant_slug=%s context=%s policies=%s",
                    getattr(tenant, "pk", None),
                    getattr(tenant, "rls_slug", None),
                    get_current_rls_debug_context(),
                    {"crm_activityrecord": get_table_policies("crm_activityrecord")},
                    exc_info=True,
                )
            return _error("creation_failed", f"Failed to create activity: {str(exc)}", status.HTTP_500_INTERNAL_SERVER_ERROR)
        except Exception as exc:
            return _error("creation_failed", f"Failed to create activity: {str(exc)}", status.HTTP_500_INTERNAL_SERVER_ERROR)
        return Response(response_payload, status=status.HTTP_201_CREATED)


@method_decorator(csrf_exempt, name="dispatch")
@extend_schema(tags=["activities"])
class ActivityDetailView(ActivitySerializerMixin, PaginationMixin, ProtectedAPIView):

    def _get_activity(self, request, activity_id) -> Optional[ActivityRecord]:
        self._ensure_tenant_schema(request)
        tenant = self._get_tenant_or_none(request)
        if tenant is None:
            return None
        base = ActivityRecord.objects.filter(tenant=tenant).select_related(
            "type", "user", "owner", "created_by", "contact", "customer", "deal", "ticket"
        )
        user = getattr(request, "user", None)
        if user and getattr(user, "is_authenticated", False):
            if not (getattr(user, "is_superuser", False) or user_has_role(user, "tenant_admin")):
                if user_has_role(user, "manager"):
                    supervised_ids = list(
                        user.direct_reports.filter(tenant=tenant).values_list("pk", flat=True)
                    )
                    visible_user_ids = [user.pk] + supervised_ids
                    base = base.filter(
                        Q(user_id__in=visible_user_ids)
                        | Q(owner_id__in=visible_user_ids)
                        | Q(created_by_id__in=visible_user_ids)
                    )
                else:
                    base = base.filter(
                        Q(user=user) | Q(owner=user) | Q(created_by=user)
                    )
        try:
            return base.get(pk=activity_id)
        except ActivityRecord.DoesNotExist:
            return None

    @extend_schema(
        summary="Get activity",
        description="Retrieve a single activity by ID.",
        responses={200: ActivityResponseSerializer},
    )
    def get(self, request, activity_id):
        activity = self._get_activity(request, activity_id)
        if not activity:
            return _error("activity_not_found", "Activity not found", status.HTTP_404_NOT_FOUND)
        return Response(self._serialize_activity(activity))

    @extend_schema(
        summary="Update activity",
        description="Partial update of an activity.",
        request=ActivityUpdateRequestSerializer,
        responses={200: ActivityResponseSerializer},
    )
    def patch(self, request, activity_id):
        activity = self._get_activity(request, activity_id)
        if not activity:
            return _error("activity_not_found", "Activity not found", status.HTTP_404_NOT_FOUND)

        payload = request.data or {}

        # Collect updates for activity manager
        updates = {}

        # Handle type resolution
        resolved_type = activity.type
        if "type" in payload or "type_key" in payload:
            type_name = payload.get("type") or payload.get("type_key")
            if type_name:
                resolved_type = ActivityType.objects.filter(tenant=activity.tenant).filter(
                    Q(key=type_name) | Q(name=type_name)
                ).first()
            else:
                resolved_type = None
            updates["type"] = resolved_type

        # Collect field updates
        field_mappings = {
            "title": "title",
            "kind": "kind",
            "source": "source",
            "visibility": "visibility",
            "status": "status",
            "scheduled_at": "scheduled_at",
            "occurred_at": "occurred_at",
            "completed_at": "completed_at",
            "duration_minutes": "duration_minutes",
            "contact_id": "contact_id",
            "customer_id": "customer_id",  # Link correction: allow updating customer
            "deal_id": "deal_id",  # Link correction: allow updating deal
            "ticket_id": "ticket_id",
            "owner_id": "owner_id",
            "created_by_id": "created_by_id",
            "tags": "tags",
            "reason": "reason",
            "needs_confirmation": "needs_confirmation",
        }

        for field_name, update_key in field_mappings.items():
            if field_name in payload:
                if field_name == "source" and payload[field_name] not in ("manual", "system", "suggestion"):
                    continue  # Skip invalid source values
                updates[update_key] = payload[field_name]

        # Handle content normalization
        if "content" in payload:
            try:
                updates["content"] = _normalize_content(
                    payload["content"],
                    kind=payload.get("kind", activity.kind),
                    activity_type=resolved_type,
                )
            except Exception as exc:
                return _error("invalid_request", str(exc), status.HTTP_400_BAD_REQUEST)

        # Use activity manager for updates
        try:
            with tenant_rls_context(activity.tenant):
                updated_activity = activity_manager.update_activity(str(activity.id), updates)
                response_payload = self._serialize_activity(updated_activity)
            return Response(response_payload)
        except Exception as exc:
            return _error("update_failed", f"Failed to update activity: {str(exc)}", status.HTTP_500_INTERNAL_SERVER_ERROR)

    @extend_schema(
        summary="Delete activity",
        description="Delete an activity.",
        responses={200: OpenApiResponse(description="Activity deleted successfully")},
    )
    def delete(self, request, activity_id):
        activity = self._get_activity(request, activity_id)
        if not activity:
            return _error("activity_not_found", "Activity not found", status.HTTP_404_NOT_FOUND)
        with tenant_rls_context(activity.tenant):
            activity.delete()
        return Response({"message": "Activity deleted successfully"})


@method_decorator(csrf_exempt, name="dispatch")
@extend_schema(tags=["activities"])
class ActivitySuggestionsView(PaginationMixin, ProtectedAPIView):
    ITEMS_KEY = "suggestions"

    def _serialize_suggestion(self, suggestion: ActivitySuggestion) -> Dict[str, Any]:
        return {
            "id": str(suggestion.pk),
            "type_key": suggestion.type_key,
            "reason": suggestion.reason,
            "confidence": suggestion.confidence,
            "suggested_at": self._isoformat(suggestion.suggested_at),
            "expires_at": self._isoformat(suggestion.expires_at) if suggestion.expires_at else None,
            "proposed_fields": suggestion.proposed_fields,
            "target_contact_id": suggestion.target_contact_id,
            "target_customer_id": str(suggestion.target_customer_id) if suggestion.target_customer_id else None,
            "target_deal_id": str(suggestion.target_deal_id) if suggestion.target_deal_id else None,
            "assigned_to_id": suggestion.assigned_to_id,
            "status": suggestion.status,
            "activity_record_id": str(suggestion.activity_record_id) if suggestion.activity_record_id else None,
            "created_by_source": suggestion.created_by_source,
        }

    def _base_queryset(self, request):
        self._ensure_tenant_schema(request)
        tenant = self._get_tenant_or_none(request)
        if tenant is None:
            return ActivitySuggestion.objects.none()
        return ActivitySuggestion.objects.filter(tenant=tenant)

    @extend_schema(
        summary="List suggestions",
        description="Paginated list of activity suggestions for the current tenant.",
        parameters=[
            OpenApiParameter("status", OpenApiTypes.STR, description="Filter by status"),
            OpenApiParameter("page", OpenApiTypes.INT, default=1),
            OpenApiParameter("limit", OpenApiTypes.INT, default=50),
        ],
        responses={200: ActivitySuggestionListResponseSerializer},
    )
    def get(self, request):
        queryset = self._base_queryset(request)
        status_filter = request.query_params.get("status")
        if status_filter:
            queryset = queryset.filter(status=status_filter)
        queryset = queryset.order_by("-suggested_at")
        return Response(self._paginate(queryset, request, self._serialize_suggestion, "suggestions"))


@method_decorator(csrf_exempt, name="dispatch")
@extend_schema(tags=["activities"])
class ActivitySuggestionAcceptView(PaginationMixin, ProtectedAPIView):
    @extend_schema(
        summary="Accept suggestion",
        description="Accept an activity suggestion, optionally with overrides.",
        request=ActivitySuggestionAcceptRequestSerializer,
        responses={200: OpenApiResponse(description="activity_id and message")},
    )
    def post(self, request, suggestion_id):
        tenant = self._get_tenant_or_none(request)
        if tenant is None:
            return _error("tenant_required", "User must belong to a tenant", status.HTTP_400_BAD_REQUEST)
        try:
            with tenant_rls_context(tenant):
                record = accept_suggestion(
                    suggestion_id,
                    request.user,
                    overrides=(request.data or {}).get("overrides"),
                    tenant=tenant,
                )
        except (
            ValueError,
            TypeError,
            PydanticValidationError,
            JsonSchemaValidationError,
        ) as e:
            return _error("invalid_state", str(e), status.HTTP_400_BAD_REQUEST)
        return Response(
            {"activity_id": str(record.pk), "message": "Suggestion accepted"},
            status=status.HTTP_200_OK,
        )


@method_decorator(csrf_exempt, name="dispatch")
@extend_schema(tags=["activities"])
class ActivitySuggestionDismissView(PaginationMixin, ProtectedAPIView):
    @extend_schema(
        summary="Dismiss suggestion",
        description="Dismiss an activity suggestion.",
        responses={200: OpenApiResponse(description="message")},
    )
    def post(self, request, suggestion_id):
        tenant = self._get_tenant_or_none(request)
        if tenant is None:
            return _error("tenant_required", "User must belong to a tenant", status.HTTP_400_BAD_REQUEST)
        try:
            with tenant_rls_context(tenant):
                dismiss_suggestion(suggestion_id, tenant=tenant)
        except ValueError as e:
            return _error("invalid_state", str(e), status.HTTP_400_BAD_REQUEST)
        return Response({"message": "Suggestion dismissed"}, status=status.HTTP_200_OK)
