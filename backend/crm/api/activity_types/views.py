from __future__ import annotations

from typing import Any, Dict, Optional

from django.db.models import Q
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt
from drf_spectacular.utils import extend_schema, OpenApiParameter
from drf_spectacular.types import OpenApiTypes
from rest_framework import status
from rest_framework.response import Response

from crm.models import ActivityType, ActivityTypeCategory, VisibilityChoices
from crm.api.activity_types.serializers import (
    ActivityTypeResponseSerializer,
    ActivityTypeCreateRequestSerializer,
    ActivityTypeUpdateRequestSerializer,
)
from crm.api.mixins import PaginationMixin, ProtectedAPIView, _error


@method_decorator(csrf_exempt, name="dispatch")
@extend_schema(tags=["activity-types"])
class ActivityTypesView(PaginationMixin, ProtectedAPIView):
    ITEMS_KEY = "activity_types"

    def _serialize_activity_type(self, at: ActivityType) -> Dict[str, Any]:
        return {
            "id": str(at.pk),
            "key": at.key,
            "label": at.label,
            "name": at.name,
            "category": at.category,
            "category_label": at.get_category_display(),
            "schema": at.schema,
            "default_duration_minutes": at.default_duration_minutes,
            "default_visibility": at.default_visibility,
            "default_status": at.default_status,
            "sla_days": at.sla_days,
            "icon": at.icon,
            "color": at.color,
            "requires_contact": at.requires_contact,
            "requires_deal": at.requires_deal,
            "title_template": at.title_template,
            "order": at.order,
        }

    def _base_queryset(self, request):
        tenant = self._get_tenant_or_none(request)
        if tenant is None:
            return ActivityType.objects.none()
        return ActivityType.objects.filter(tenant=tenant)

    @extend_schema(
        summary="List activity types",
        parameters=[
            OpenApiParameter("category", OpenApiTypes.STR),
            OpenApiParameter("search", OpenApiTypes.STR),
            OpenApiParameter("page", OpenApiTypes.INT, default=1),
            OpenApiParameter("limit", OpenApiTypes.INT, default=50),
        ],
        responses={200: ActivityTypeResponseSerializer(many=True)},
    )
    def get(self, request):
        queryset = self._base_queryset(request)
        category = request.query_params.get("category")
        if category:
            queryset = queryset.filter(category=category)
        search = (request.query_params.get("search") or "").strip()
        if search:
            queryset = queryset.filter(
                Q(key__icontains=search) | Q(label__icontains=search)
            )
        queryset = queryset.order_by("order", "label")
        return Response(
            self._paginate(queryset, request, self._serialize_activity_type, "activity_types")
        )

    @extend_schema(summary="Create activity type", request=ActivityTypeCreateRequestSerializer, responses={201: ActivityTypeResponseSerializer})
    def post(self, request):
        tenant = self._get_tenant_or_none(request)
        if tenant is None:
            return _error(
                "tenant_required",
                "User must belong to a tenant",
                status.HTTP_400_BAD_REQUEST,
            )
        payload = request.data or {}
        key = (payload.get("key") or "").strip()
        if not key:
            return _error(
                "key_required",
                "key is required",
                status.HTTP_400_BAD_REQUEST,
            )
        if ActivityType.objects.filter(tenant=tenant, key=key).exists():
            return _error(
                "key_exists",
                f"Activity type with key '{key}' already exists",
                status.HTTP_400_BAD_REQUEST,
            )
        label = (payload.get("label") or key).strip()
        at = ActivityType.objects.create(
            tenant=tenant,
            key=key,
            label=label,
            name=payload.get("name", label),
            category=payload.get("category", ActivityTypeCategory.OTHER),
            schema=payload.get("schema"),
            default_duration_minutes=payload.get("default_duration_minutes"),
            default_visibility=payload.get("default_visibility", VisibilityChoices.PUBLIC),
            default_status=payload.get("default_status", "completed"),
            sla_days=payload.get("sla_days"),
            icon=payload.get("icon", ""),
            color=payload.get("color", ""),
            requires_contact=payload.get("requires_contact", False),
            requires_deal=payload.get("requires_deal", False),
            title_template=payload.get("title_template", ""),
            order=payload.get("order", 0),
        )
        return Response(
            self._serialize_activity_type(at),
            status=status.HTTP_201_CREATED,
        )


@method_decorator(csrf_exempt, name="dispatch")
@extend_schema(tags=["activity-types"])
class ActivityTypeDetailView(PaginationMixin, ProtectedAPIView):
    def _get_activity_type(self, request, type_id) -> Optional[ActivityType]:
        tenant = self._get_tenant_or_none(request)
        if tenant is None:
            return None
        try:
            return ActivityType.objects.filter(tenant=tenant).get(pk=type_id)
        except ActivityType.DoesNotExist:
            return None

    def _serialize_activity_type(self, at: ActivityType) -> Dict[str, Any]:
        return {
            "id": str(at.pk),
            "key": at.key,
            "label": at.label,
            "name": at.name,
            "category": at.category,
            "category_label": at.get_category_display(),
            "schema": at.schema,
            "default_duration_minutes": at.default_duration_minutes,
            "default_visibility": at.default_visibility,
            "default_status": at.default_status,
            "sla_days": at.sla_days,
            "icon": at.icon,
            "color": at.color,
            "requires_contact": at.requires_contact,
            "requires_deal": at.requires_deal,
            "title_template": at.title_template,
            "order": at.order,
        }

    @extend_schema(summary="Get activity type", responses={200: ActivityTypeResponseSerializer})
    def get(self, request, type_id):
        at = self._get_activity_type(request, type_id)
        if not at:
            return _error(
                "activity_type_not_found",
                "Activity type not found",
                status.HTTP_404_NOT_FOUND,
            )
        return Response(self._serialize_activity_type(at))

    @extend_schema(summary="Update activity type", request=ActivityTypeUpdateRequestSerializer, responses={200: ActivityTypeResponseSerializer})
    def patch(self, request, type_id):
        at = self._get_activity_type(request, type_id)
        if not at:
            return _error(
                "activity_type_not_found",
                "Activity type not found",
                status.HTTP_404_NOT_FOUND,
            )
        payload = request.data or {}
        allowed = (
            "label", "name", "category", "schema",
            "default_duration_minutes", "default_visibility", "default_status",
            "sla_days", "icon", "color", "requires_contact", "requires_deal",
            "title_template", "order",
        )
        for key in allowed:
            if key in payload:
                setattr(at, key, payload[key])
        at.save()
        return Response(self._serialize_activity_type(at))
