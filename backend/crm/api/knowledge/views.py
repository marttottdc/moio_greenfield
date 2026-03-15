from __future__ import annotations

import logging
from typing import Any, Dict

from django.db.models import Q
from tenancy.resolution import _current_connection_schema
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt
from drf_spectacular.utils import extend_schema, OpenApiExample, OpenApiParameter
from rest_framework import status
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response

from crm.models import KnowledgeItem
from crm.api.knowledge.serializers import KnowledgeItemSerializer
from crm.api.mixins import ProtectedAPIView

_log = logging.getLogger("tenancy_trace")


KNOWLEDGE_EXAMPLES = [
    OpenApiExample(
        "Service Zones",
        summary="Geographical service coverage areas",
        description="Define service zones with coverage radius and pricing multipliers for delivery or on-site services",
        value={
            "title": "Buenos Aires Service Zones",
            "description": "Delivery zones and coverage areas for Buenos Aires metropolitan area",
            "type": "SERVICE",
            "category": "operations",
            "visibility": "AGENT_ONLY",
            "data": {
                "zones": [
                    {"name": "CABA", "radius_km": 15, "base_fee": 500, "multiplier": 1.0},
                    {"name": "GBA Norte", "radius_km": 30, "base_fee": 800, "multiplier": 1.3},
                    {"name": "GBA Sur", "radius_km": 35, "base_fee": 900, "multiplier": 1.5},
                ],
                "default_currency": "ARS",
                "max_distance_km": 50,
            },
        },
        request_only=True,
    ),
    OpenApiExample(
        "Business Hours",
        summary="Operating schedule and availability",
        description="Store business hours, holidays, and special schedules for customer inquiries",
        value={
            "title": "Store Operating Hours",
            "description": "Regular business hours and holiday schedule",
            "type": "POLICY",
            "category": "operations",
            "visibility": "PUBLIC",
            "data": {
                "timezone": "America/Argentina/Buenos_Aires",
                "regular_hours": {
                    "monday": {"open": "09:00", "close": "18:00"},
                    "tuesday": {"open": "09:00", "close": "18:00"},
                    "wednesday": {"open": "09:00", "close": "18:00"},
                    "thursday": {"open": "09:00", "close": "18:00"},
                    "friday": {"open": "09:00", "close": "18:00"},
                    "saturday": {"open": "10:00", "close": "14:00"},
                    "sunday": None,
                },
                "holidays": ["2025-01-01", "2025-12-25"],
                "special_notes": "Extended hours during December",
            },
        },
        request_only=True,
    ),
    OpenApiExample(
        "Pricing Table",
        summary="Product or service pricing structure",
        description="Structured pricing with tiers, discounts, and promotional offers",
        value={
            "title": "Subscription Plans",
            "description": "Monthly subscription tiers and pricing",
            "type": "PRODUCT",
            "category": "pricing",
            "visibility": "PUBLIC",
            "data": {
                "currency": "USD",
                "plans": [
                    {"name": "Basic", "monthly": 29, "annual": 290, "features": ["5 users", "10GB storage"]},
                    {"name": "Pro", "monthly": 79, "annual": 790, "features": ["25 users", "100GB storage", "Priority support"]},
                    {"name": "Enterprise", "monthly": None, "annual": None, "features": ["Unlimited users", "Custom storage", "Dedicated support"], "contact_sales": True},
                ],
                "trial_days": 14,
                "discount_codes": [{"code": "SAVE20", "percent": 20, "expires": "2025-12-31"}],
            },
        },
        request_only=True,
    ),
    OpenApiExample(
        "FAQ",
        summary="Frequently asked questions",
        description="Q&A pairs for AI agent to answer common customer inquiries",
        value={
            "title": "Shipping FAQ",
            "description": "Common questions about shipping and delivery",
            "type": "FAQ",
            "category": "support",
            "visibility": "PUBLIC",
            "data": {
                "questions": [
                    {
                        "q": "How long does shipping take?",
                        "a": "Standard shipping takes 3-5 business days. Express shipping is 1-2 business days.",
                    },
                    {
                        "q": "Do you ship internationally?",
                        "a": "Yes, we ship to over 50 countries. International shipping takes 7-14 business days.",
                    },
                    {
                        "q": "Can I track my order?",
                        "a": "Yes, you will receive a tracking number via email once your order ships.",
                    },
                ],
            },
        },
        request_only=True,
    ),
    OpenApiExample(
        "Return Policy",
        summary="Terms and conditions for returns",
        description="Policy document for AI agent reference when handling return requests",
        value={
            "title": "Return and Refund Policy",
            "description": "Terms for product returns and refund processing",
            "type": "POLICY",
            "category": "legal",
            "visibility": "PUBLIC",
            "url": "https://example.com/returns",
            "data": {
                "return_window_days": 30,
                "conditions": [
                    "Item must be unused and in original packaging",
                    "Receipt or proof of purchase required",
                    "Sale items are final sale",
                ],
                "refund_method": "Original payment method",
                "processing_days": 5,
                "exceptions": ["Perishable goods", "Custom orders", "Digital products"],
            },
        },
        request_only=True,
    ),
]

KNOWLEDGE_RESPONSE_EXAMPLE = OpenApiExample(
    "Knowledge Item Response",
    summary="Full knowledge item with metadata",
    value={
        "id": "550e8400-e29b-41d4-a716-446655440000",
        "title": "Store Operating Hours",
        "description": "Regular business hours and holiday schedule",
        "url": None,
        "type": "POLICY",
        "category": "operations",
        "visibility": "PUBLIC",
        "slug": "store-operating-hours",
        "data": {
            "timezone": "America/Argentina/Buenos_Aires",
            "regular_hours": {
                "monday": {"open": "09:00", "close": "18:00"},
            },
        },
        "created": "2025-01-15T10:30:00Z",
        "modified": "2025-01-20T14:45:00Z",
    },
    response_only=True,
)


def _error(code: str, message: str, http_status: int) -> Response:
    return Response({"error": code, "message": message}, status=http_status)


@method_decorator(csrf_exempt, name="dispatch")
class KnowledgeListView(ProtectedAPIView):
    """
    API endpoint for listing and creating knowledge items.
    
    Knowledge items store structured data that AI agents can reference when
    responding to customer inquiries. Common use cases include service zones,
    business hours, pricing tables, FAQs, and policy documents.
    """
    serializer_class = KnowledgeItemSerializer

    def _base_queryset(self, request):
        tenant = getattr(request, "tenant", None) or getattr(request.user, "tenant", None)
        if tenant is None:
            return KnowledgeItem.objects.none()
        return KnowledgeItem.objects.filter(tenant=tenant)

    def _paginate(self, queryset, request) -> Dict[str, Any]:
        try:
            page = int(request.query_params.get("page", 1))
        except ValueError:
            raise ValidationError({"page": "Must be an integer"})
        try:
            limit = int(request.query_params.get("limit", 50))
        except ValueError:
            raise ValidationError({"limit": "Must be an integer"})
        limit = max(1, min(limit, 100))
        page = max(page, 1)
        start = (page - 1) * limit
        end = start + limit
        _log.debug(
            "knowledge_list: request.tenant=%s request.user.tenant=%s conn_schema=%s (before count)",
            getattr(request, "tenant", None) and getattr(getattr(request, "tenant", None), "schema_name", ""),
            getattr(getattr(request, "user", None), "tenant", None) and getattr(getattr(getattr(request, "user", None), "tenant", None), "schema_name", ""),
            _current_connection_schema(),
        )
        total = queryset.count()
        serializer = self.serializer_class(queryset[start:end], many=True)
        pagination = {
            "current_page": page,
            "total_pages": (total + limit - 1) // limit if limit else 1,
            "total_items": total,
            "items_per_page": limit,
        }
        return {"items": serializer.data, "pagination": pagination}

    def get(self, request):
        if getattr(request, "tenant", None) is None:
            return _error("tenant_required", "Tenant context is required.", status.HTTP_403_FORBIDDEN)
        queryset = self._base_queryset(request)

        search = (request.query_params.get("search") or "").strip()
        if search:
            queryset = queryset.filter(
                Q(title__icontains=search)
                | Q(description__icontains=search)
                | Q(category__icontains=search)
            )

        type_filter = request.query_params.get("type")
        if type_filter:
            queryset = queryset.filter(type=type_filter)

        category_filter = request.query_params.get("category")
        if category_filter:
            queryset = queryset.filter(category=category_filter)

        sort_by = request.query_params.get("sort_by", "created")
        order = request.query_params.get("order", "desc")
        prefix = "-" if order == "desc" else ""
        
        allowed_sort_fields = {"created", "modified", "title", "type", "category"}
        if sort_by not in allowed_sort_fields:
            sort_by = "created"
        
        queryset = queryset.order_by(f"{prefix}{sort_by}")
        return Response(self._paginate(queryset, request))

    get = extend_schema(
        summary="List knowledge items",
        description="Retrieve a paginated list of knowledge items with optional filtering",
        parameters=[
            OpenApiParameter(name="search", description="Search in title, description, and category", type=str),
            OpenApiParameter(name="type", description="Filter by type (FAQ, PRODUCT, POLICY, SERVICE, ARTICLE)", type=str),
            OpenApiParameter(name="category", description="Filter by category", type=str),
            OpenApiParameter(name="sort_by", description="Sort field (created, modified, title, type, category)", type=str),
            OpenApiParameter(name="order", description="Sort order (asc, desc)", type=str),
            OpenApiParameter(name="page", description="Page number", type=int),
            OpenApiParameter(name="limit", description="Items per page (max 100)", type=int),
        ],
        tags=["Knowledge"],
    )(get)

    @extend_schema(
        summary="Create knowledge item",
        description="Create a new knowledge item with structured data for AI agent reference",
        request=KnowledgeItemSerializer,
        responses={201: KnowledgeItemSerializer},
        examples=KNOWLEDGE_EXAMPLES + [KNOWLEDGE_RESPONSE_EXAMPLE],
        tags=["Knowledge"],
    )
    def post(self, request):
        if getattr(request, "tenant", None) is None:
            return _error("tenant_required", "Tenant context is required.", status.HTTP_403_FORBIDDEN)
        serializer = self.serializer_class(data=request.data, context={"request": request})
        try:
            serializer.is_valid(raise_exception=True)
        except ValidationError as exc:
            return Response(exc.detail, status=status.HTTP_400_BAD_REQUEST)

        serializer.save()
        return Response(serializer.data, status=status.HTTP_201_CREATED)


@method_decorator(csrf_exempt, name="dispatch")
class KnowledgeDetailView(ProtectedAPIView):
    """
    API endpoint for retrieving, updating, and deleting individual knowledge items.
    """
    serializer_class = KnowledgeItemSerializer

    def _get_item(self, request, item_id) -> KnowledgeItem | None:
        tenant = getattr(request, "tenant", None) or getattr(request.user, "tenant", None)
        if tenant is None:
            return None
        return KnowledgeItem.objects.filter(tenant=tenant, pk=item_id).first()

    @extend_schema(
        summary="Get knowledge item",
        description="Retrieve a single knowledge item by ID",
        responses={200: KnowledgeItemSerializer},
        examples=[KNOWLEDGE_RESPONSE_EXAMPLE],
        tags=["Knowledge"],
    )
    def get(self, request, item_id):
        if getattr(request, "tenant", None) is None:
            return _error("tenant_required", "Tenant context is required.", status.HTTP_403_FORBIDDEN)
        item = self._get_item(request, item_id)
        if not item:
            return _error("not_found", "Knowledge item not found", status.HTTP_404_NOT_FOUND)
        serializer = self.serializer_class(item)
        return Response(serializer.data)

    @extend_schema(
        summary="Partially update knowledge item",
        description="Update specific fields of a knowledge item",
        request=KnowledgeItemSerializer,
        responses={200: KnowledgeItemSerializer},
        examples=KNOWLEDGE_EXAMPLES + [KNOWLEDGE_RESPONSE_EXAMPLE],
        tags=["Knowledge"],
    )
    def patch(self, request, item_id):
        if getattr(request, "tenant", None) is None:
            return _error("tenant_required", "Tenant context is required.", status.HTTP_403_FORBIDDEN)
        item = self._get_item(request, item_id)
        if not item:
            return _error("not_found", "Knowledge item not found", status.HTTP_404_NOT_FOUND)

        serializer = self.serializer_class(item, data=request.data, partial=True, context={"request": request})
        try:
            serializer.is_valid(raise_exception=True)
        except ValidationError as exc:
            return Response(exc.detail, status=status.HTTP_400_BAD_REQUEST)

        serializer.save()
        return Response(serializer.data)

    @extend_schema(
        summary="Replace knowledge item",
        description="Fully replace a knowledge item with new data",
        request=KnowledgeItemSerializer,
        responses={200: KnowledgeItemSerializer},
        examples=KNOWLEDGE_EXAMPLES + [KNOWLEDGE_RESPONSE_EXAMPLE],
        tags=["Knowledge"],
    )
    def put(self, request, item_id):
        if getattr(request, "tenant", None) is None:
            return _error("tenant_required", "Tenant context is required.", status.HTTP_403_FORBIDDEN)
        item = self._get_item(request, item_id)
        if not item:
            return _error("not_found", "Knowledge item not found", status.HTTP_404_NOT_FOUND)

        serializer = self.serializer_class(item, data=request.data, context={"request": request})
        try:
            serializer.is_valid(raise_exception=True)
        except ValidationError as exc:
            return Response(exc.detail, status=status.HTTP_400_BAD_REQUEST)

        serializer.save()
        return Response(serializer.data)

    @extend_schema(
        summary="Delete knowledge item",
        description="Permanently remove a knowledge item",
        responses={204: None},
        tags=["Knowledge"],
    )
    def delete(self, request, item_id):
        if getattr(request, "tenant", None) is None:
            return _error("tenant_required", "Tenant context is required.", status.HTTP_403_FORBIDDEN)
        item = self._get_item(request, item_id)
        if not item:
            return _error("not_found", "Knowledge item not found", status.HTTP_404_NOT_FOUND)

        item.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)
