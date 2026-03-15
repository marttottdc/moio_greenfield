from __future__ import annotations

from typing import Any, Dict, Optional

from django.db.models import Q
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt
from drf_spectacular.utils import extend_schema, OpenApiParameter, OpenApiResponse
from drf_spectacular.types import OpenApiTypes
from rest_framework import status
from rest_framework.response import Response

from crm.models import Tag
from crm.api.tags.serializers import TagResponseSerializer, TagCreateRequestSerializer, TagUpdateRequestSerializer
from crm.api.mixins import PaginationMixin, ProtectedAPIView, _error


@method_decorator(csrf_exempt, name="dispatch")
@extend_schema(tags=["tags"])
class TagsView(PaginationMixin, ProtectedAPIView):
    ITEMS_KEY = "tags"

    def _serialize_tag(self, tag: Tag) -> Dict[str, Any]:
        return {
            "id": str(tag.pk),
            "name": tag.name,
            "slug": tag.slug,
            "description": tag.description,
            "context": tag.context,
            "created_at": self._isoformat(tag.created_at),
            "updated_at": self._isoformat(tag.updated_at),
        }

    def _base_queryset(self, request):
        tenant = self._get_tenant_or_none(request)
        if tenant is None:
            return Tag.objects.none()
        return Tag.objects.filter(tenant=tenant)

    @extend_schema(
        summary="List tags",
        parameters=[
            OpenApiParameter("search", OpenApiTypes.STR),
            OpenApiParameter("context", OpenApiTypes.STR),
            OpenApiParameter("sort_by", OpenApiTypes.STR, default="name"),
            OpenApiParameter("order", OpenApiTypes.STR, default="asc"),
            OpenApiParameter("page", OpenApiTypes.INT, default=1),
            OpenApiParameter("limit", OpenApiTypes.INT, default=50),
        ],
        responses={200: TagResponseSerializer(many=True)},
    )
    def get(self, request):
        queryset = self._base_queryset(request)

        search = (request.query_params.get("search") or "").strip()
        if search:
            queryset = queryset.filter(
                Q(name__icontains=search)
                | Q(description__icontains=search)
                | Q(slug__icontains=search)
            )

        context_filter = request.query_params.get("context")
        if context_filter:
            queryset = queryset.filter(context=context_filter)

        sort_by = request.query_params.get("sort_by", "name")
        order = request.query_params.get("order", "asc")
        prefix = "-" if order == "desc" else ""

        allowed_sort_fields = {"name", "created_at", "updated_at", "slug"}
        if sort_by not in allowed_sort_fields:
            sort_by = "name"

        queryset = queryset.order_by(f"{prefix}{sort_by}")
        return Response(self._paginate(queryset, request, self._serialize_tag, "tags"))

    @extend_schema(summary="Create tag", request=TagCreateRequestSerializer, responses={201: TagResponseSerializer})
    def post(self, request):
        tenant = self._get_tenant_or_none(request)
        if tenant is None:
            return _error("tenant_required", "User must belong to a tenant", status.HTTP_400_BAD_REQUEST)

        payload = request.data or {}
        name = (payload.get("name") or "").strip()
        if not name:
            return _error("invalid_request", "name is required", status.HTTP_400_BAD_REQUEST)

        tag = Tag(
            tenant=tenant,
            name=name,
            description=payload.get("description", ""),
            context=payload.get("context"),
        )
        tag.save()
        return Response(self._serialize_tag(tag), status=status.HTTP_201_CREATED)


@method_decorator(csrf_exempt, name="dispatch")
@extend_schema(tags=["tags"])
class TagDetailView(PaginationMixin, ProtectedAPIView):

    def _get_tag(self, request, tag_id) -> Optional[Tag]:
        tenant = self._get_tenant_or_none(request)
        if tenant is None:
            return None
        try:
            return Tag.objects.filter(tenant=tenant).get(pk=tag_id)
        except Tag.DoesNotExist:
            return None

    def _serialize_tag(self, tag: Tag) -> Dict[str, Any]:
        return {
            "id": str(tag.pk),
            "name": tag.name,
            "slug": tag.slug,
            "description": tag.description,
            "context": tag.context,
            "created_at": self._isoformat(tag.created_at),
            "updated_at": self._isoformat(tag.updated_at),
        }

    @extend_schema(summary="Get tag", responses={200: TagResponseSerializer})
    def get(self, request, tag_id):
        tag = self._get_tag(request, tag_id)
        if not tag:
            return _error("tag_not_found", "Tag not found", status.HTTP_404_NOT_FOUND)
        return Response(self._serialize_tag(tag))

    @extend_schema(summary="Update tag", request=TagUpdateRequestSerializer, responses={200: TagResponseSerializer})
    def patch(self, request, tag_id):
        tag = self._get_tag(request, tag_id)
        if not tag:
            return _error("tag_not_found", "Tag not found", status.HTTP_404_NOT_FOUND)

        payload = request.data or {}
        if "name" in payload:
            tag.name = payload["name"]
        if "description" in payload:
            tag.description = payload["description"]
        if "context" in payload:
            tag.context = payload["context"]

        tag.save()
        return Response(self._serialize_tag(tag))

    @extend_schema(summary="Delete tag", responses={200: OpenApiResponse(description="message")})
    def delete(self, request, tag_id):
        tag = self._get_tag(request, tag_id)
        if not tag:
            return _error("tag_not_found", "Tag not found", status.HTTP_404_NOT_FOUND)
        tag.delete()
        return Response({"message": "Tag deleted successfully"})
