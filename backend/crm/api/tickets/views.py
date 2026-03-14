from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Optional

from django.db.models import Count, Q
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt
from drf_spectacular.utils import extend_schema, OpenApiParameter, OpenApiExample, OpenApiResponse
from drf_spectacular.types import OpenApiTypes
from rest_framework import status, serializers
from rest_framework.response import Response

from crm.api.mixins import ProtectedAPIView, TicketAPIMixin, _error
from crm.models import Contact, Ticket, TicketComment, TicketOriginChoices
from crm.services.ticket_service import TicketService
from crm.events.ticket_events import emit_ticket_created, emit_ticket_updated, emit_ticket_closed
from chatbot.models.agent_session import AgentSession
from moio_platform.api_schemas import Tags, STANDARD_ERRORS


# ─────────────────────────────────────────────────────────────────────────────
# Response Serializers for Documentation
# ─────────────────────────────────────────────────────────────────────────────

class TicketResponseSerializer(serializers.Serializer):
    """Ticket response schema for API documentation."""
    id = serializers.UUIDField(help_text="Unique ticket identifier")
    title = serializers.CharField(help_text="Ticket title/subject")
    description = serializers.CharField(help_text="Ticket description")
    status = serializers.ChoiceField(choices=["O", "A", "I", "W", "P", "C"], help_text="Status: O=Open, A=Assigned, I=In Progress, W=Waiting, P=Pending, C=Closed")
    priority = serializers.CharField(help_text="Priority level")
    ticket_type = serializers.CharField(allow_null=True, help_text="Ticket type")
    contact_id = serializers.UUIDField(help_text="Associated contact ID")
    contact_name = serializers.CharField(help_text="Contact full name")
    assigned_id = serializers.UUIDField(allow_null=True, help_text="Assigned user ID")
    assigned_name = serializers.CharField(allow_null=True, help_text="Assigned user name")
    origin_type = serializers.CharField(help_text="Origin: manual, chatbot, email, phone")
    origin_ref = serializers.CharField(help_text="Reference identifier from origin")
    created_at = serializers.DateTimeField(help_text="Creation timestamp")
    updated_at = serializers.DateTimeField(help_text="Last update timestamp")


class TicketListResponseSerializer(serializers.Serializer):
    """Paginated ticket list response."""
    tickets = TicketResponseSerializer(many=True)
    pagination = serializers.DictField(help_text="Pagination metadata")


class TicketCommentSerializer(serializers.Serializer):
    """Ticket comment schema."""
    id = serializers.UUIDField()
    content = serializers.CharField()
    author_id = serializers.UUIDField()
    author_name = serializers.CharField()
    created_at = serializers.DateTimeField()


class TicketSummaryResponseSerializer(serializers.Serializer):
    """Ticket summary/stats response."""
    total = serializers.IntegerField(help_text="Total ticket count")
    open = serializers.IntegerField(help_text="Open tickets count")
    closed = serializers.IntegerField(help_text="Closed tickets count")


# ─────────────────────────────────────────────────────────────────────────────
# Ticket Views
# ─────────────────────────────────────────────────────────────────────────────

@method_decorator(csrf_exempt, name="dispatch")
class TicketListCreateView(TicketAPIMixin, ProtectedAPIView):
    """List and create support tickets."""

    @extend_schema(
        summary="List tickets",
        description="Retrieve a paginated list of tickets. Supports filtering by status and search.",
        tags=[Tags.CRM_TICKETS],
        parameters=[
            OpenApiParameter("status", OpenApiTypes.STR, description="Filter by status: O, A, I, W, P, C"),
            OpenApiParameter("search", OpenApiTypes.STR, description="Search in title, description, contact name"),
            OpenApiParameter("page", OpenApiTypes.INT, description="Page number", default=1),
            OpenApiParameter("limit", OpenApiTypes.INT, description="Items per page (max 100)", default=20),
        ],
        responses={200: TicketListResponseSerializer, **STANDARD_ERRORS},
    )
    def get(self, request):
        try:
            page = int(request.query_params.get("page", 1))
        except ValueError:
            return _error("invalid_page", "page must be an integer", status.HTTP_400_BAD_REQUEST)
        try:
            limit = int(request.query_params.get("limit", 20))
        except ValueError:
            return _error("invalid_limit", "limit must be an integer", status.HTTP_400_BAD_REQUEST)
        limit = max(1, min(limit, 100))
        page = max(page, 1)
        start = (page - 1) * limit
        end = start + limit

        queryset = self._tenant_queryset(request)

        status_filter = request.query_params.get("status")
        if status_filter:
            queryset = queryset.filter(status=status_filter)

        search = (request.query_params.get("search") or "").strip()
        if search:
            queryset = queryset.filter(
                Q(title__icontains=search)
                | Q(description__icontains=search)
                | Q(contact__fullname__icontains=search)
            )

        queryset = queryset.order_by("-created")
        total = queryset.count()
        tickets = list(queryset[start:end])
        payload = {
            "tickets": [self._serialize_ticket(ticket) for ticket in tickets],
            "pagination": {
                "current_page": page,
                "total_pages": (total + limit - 1) // limit if limit else 1,
                "total_items": total,
                "items_per_page": limit,
            },
        }
        return Response(payload)

    @extend_schema(
        summary="Create ticket",
        description="Create a new support ticket. Required: title, contact_id. Optional: description, status, priority, type, origin_type, origin_ref.",
        tags=[Tags.CRM_TICKETS],
        responses={201: TicketResponseSerializer, **STANDARD_ERRORS},
    )
    def post(self, request):
        payload = request.data or {}
        tenant = getattr(request.user, "tenant", None)
        if tenant is None:
            return _error("tenant_required", "User must belong to a tenant", status.HTTP_400_BAD_REQUEST)

        raw_title = payload.get("title") or ""
        title = str(raw_title).strip()
        if not title:
            return _error("invalid_request", "title is required", status.HTTP_400_BAD_REQUEST)

        contact = self._get_contact_for_payload(payload, tenant)
        if contact is None:
            return _error("invalid_contact", "valid contact is required", status.HTTP_400_BAD_REQUEST)

        ticket_type, ticket_priority = self._resolve_type_priority(payload, tenant)

        origin_type = payload.get("origin_type", TicketOriginChoices.MANUAL)
        if origin_type not in TicketOriginChoices.values:
            return _error("invalid_origin_type", f"origin_type must be one of: {', '.join(TicketOriginChoices.values)}", status.HTTP_400_BAD_REQUEST)

        origin_ref = str(payload.get("origin_ref", "")).strip()
        origin_session = None

        origin_session_id = payload.get("origin_session_id")
        if origin_session_id:
            origin_session = AgentSession.objects.filter(
                session=origin_session_id,
                tenant=tenant
            ).first()
            if origin_session is None:
                return _error("invalid_origin_session", "origin_session_id not found", status.HTTP_400_BAD_REQUEST)
            if not origin_ref:
                origin_ref = str(origin_session_id)
            if origin_type == TicketOriginChoices.MANUAL:
                origin_type = TicketOriginChoices.CHATBOT

        ticket = Ticket.objects.create(
            tenant=tenant,
            title=title,
            description=payload.get("description", ""),
            contact=contact,
            status=payload.get("status", Ticket.Status.OPEN),
            priority=ticket_priority,
            ticket_type=ticket_type,
            created_by=request.user,
            origin_type=origin_type,
            origin_ref=origin_ref,
            origin_session=origin_session,
        )
        
        emit_ticket_created(ticket, request.user.id)
        
        return Response(self._serialize_ticket(ticket), status=status.HTTP_201_CREATED)


@method_decorator(csrf_exempt, name="dispatch")
class TicketDetailView(TicketAPIMixin, ProtectedAPIView):
    """Ticket detail, update, and delete operations."""

    @extend_schema(
        summary="Get ticket details",
        description="Retrieve details of a specific ticket.",
        tags=[Tags.CRM_TICKETS],
        responses={200: TicketResponseSerializer, **STANDARD_ERRORS},
    )
    def get(self, request, ticket_id):
        ticket = self._get_ticket(request, ticket_id)
        if ticket is None:
            return _error("ticket_not_found", "Ticket not found", status.HTTP_404_NOT_FOUND)
        return Response(self._serialize_ticket(ticket))

    @extend_schema(
        summary="Update ticket",
        description="Partially update a ticket. Emits `ticket.updated` and optionally `ticket.closed` events.",
        tags=[Tags.CRM_TICKETS],
        responses={200: TicketResponseSerializer, **STANDARD_ERRORS},
    )
    def patch(self, request, ticket_id):
        ticket = self._get_ticket(request, ticket_id)
        if ticket is None:
            return _error("ticket_not_found", "Ticket not found", status.HTTP_404_NOT_FOUND)

        payload = request.data or {}
        fields_to_update = []

        if "title" in payload:
            raw_title = payload.get("title") or ""
            title = str(raw_title).strip()
            if not title:
                return _error("invalid_request", "title cannot be empty", status.HTTP_400_BAD_REQUEST)
            ticket.title = title
            fields_to_update.append("title")

        if "description" in payload:
            ticket.description = payload.get("description", "")
            fields_to_update.append("description")

        old_status = ticket.status
        if "status" in payload:
            new_status = payload.get("status")
            ticket.status = new_status
            fields_to_update.append("status")
            if new_status == "W" and old_status != "W":
                ticket.waiting_since = timezone.now()
                fields_to_update.append("waiting_since")
            elif new_status != "W" and old_status == "W":
                ticket.waiting_since = None
                fields_to_update.append("waiting_since")

        if "priority" in payload:
            ticket.priority = payload.get("priority")
            fields_to_update.append("priority")

        if "type" in payload:
            ticket.ticket_type = payload.get("type")
            fields_to_update.append("ticket_type")

        if "contact_id" in payload:
            tenant = getattr(request.user, "tenant", None)
            contact = self._get_contact_for_payload(payload, tenant)
            if contact is None:
                return _error("invalid_contact", "valid contact is required", status.HTTP_400_BAD_REQUEST)
            ticket.contact = contact
            fields_to_update.append("contact")

        if "assigned" in payload:
            tenant = getattr(request.user, "tenant", None)
            assignee = Ticket.resolve_assignee(payload.get("assigned"), tenant)
            ticket.assigned = assignee
            fields_to_update.append("assigned")

        if "target" in payload:
            target_value = payload.get("target")
            if target_value is None:
                ticket.target = None
            else:
                parsed_target = parse_datetime(str(target_value))
                if parsed_target is None:
                    return _error("invalid_target", "target must be a valid ISO datetime", status.HTTP_400_BAD_REQUEST)
                ticket.target = parsed_target
            fields_to_update.append("target")

        tenant = getattr(request.user, "tenant", None)
        if "waiting_for" in payload:
            waiting_for_value = payload.get("waiting_for")
            if waiting_for_value is None:
                ticket.waiting_for = None
            else:
                waiting_contact = Contact.objects.filter(
                    user_id=waiting_for_value, tenant=tenant
                ).first()
                if waiting_contact is None:
                    return _error("invalid_waiting_for", "waiting_for contact not found", status.HTTP_400_BAD_REQUEST)
                ticket.waiting_for = waiting_contact
            fields_to_update.append("waiting_for")

        if "origin_type" in payload:
            new_origin_type = payload.get("origin_type")
            if new_origin_type not in TicketOriginChoices.values:
                return _error("invalid_origin_type", f"origin_type must be one of: {', '.join(TicketOriginChoices.values)}", status.HTTP_400_BAD_REQUEST)
            ticket.origin_type = new_origin_type
            fields_to_update.append("origin_type")

        if "origin_ref" in payload:
            ticket.origin_ref = str(payload.get("origin_ref", "")).strip()
            fields_to_update.append("origin_ref")

        if "origin_session_id" in payload:
            origin_session_id = payload.get("origin_session_id")
            if origin_session_id is None:
                ticket.origin_session = None
            else:
                origin_session = AgentSession.objects.filter(
                    session=origin_session_id,
                    tenant=tenant
                ).first()
                if origin_session is None:
                    return _error("invalid_origin_session", "origin_session_id not found", status.HTTP_400_BAD_REQUEST)
                ticket.origin_session = origin_session
                if not ticket.origin_ref:
                    ticket.origin_ref = str(origin_session_id)
                    if "origin_ref" not in fields_to_update:
                        fields_to_update.append("origin_ref")
                if ticket.origin_type == TicketOriginChoices.MANUAL:
                    ticket.origin_type = TicketOriginChoices.CHATBOT
                    if "origin_type" not in fields_to_update:
                        fields_to_update.append("origin_type")
            fields_to_update.append("origin_session")

        if fields_to_update:
            fields_to_update.append("updated")
            ticket.save(update_fields=fields_to_update)
            
            # Emit events based on changes
            emit_ticket_updated(ticket, request.user.id, fields_to_update)
            
            # If ticket was closed, also emit closed event
            if "status" in fields_to_update and ticket.status == "C":
                emit_ticket_closed(ticket, request.user.id)

        return Response(self._serialize_ticket(ticket))

    @extend_schema(
        summary="Delete ticket",
        description="Permanently delete a ticket.",
        tags=[Tags.CRM_TICKETS],
        responses={200: OpenApiResponse(description="Ticket deleted successfully"), **STANDARD_ERRORS},
    )
    def delete(self, request, ticket_id):
        ticket = self._get_ticket(request, ticket_id)
        if ticket is None:
            return _error("ticket_not_found", "Ticket not found", status.HTTP_404_NOT_FOUND)
        ticket.delete()
        return Response({"message": "Ticket deleted successfully"})


@method_decorator(csrf_exempt, name="dispatch")
class TicketCommentsView(TicketAPIMixin, ProtectedAPIView):
    """List and add ticket comments."""

    @extend_schema(
        summary="List ticket comments",
        description="Get all comments for a ticket, ordered by creation date.",
        tags=[Tags.CRM_TICKETS],
        responses={
            200: OpenApiResponse(description="List of comments"),
            **STANDARD_ERRORS,
        },
    )
    def get(self, request, ticket_id):
        ticket = self._get_ticket(request, ticket_id)
        if ticket is None:
            return _error("ticket_not_found", "Ticket not found", status.HTTP_404_NOT_FOUND)
        comments = TicketComment.objects.filter(ticket=ticket).order_by("created")
        payload = {
            "comments": [self._serialize_comment(comment) for comment in comments],
            "count": comments.count(),
        }
        return Response(payload)

    @extend_schema(
        summary="Add comment",
        description="Add a new comment to a ticket. Requires: content (string).",
        tags=[Tags.CRM_TICKETS],
        responses={201: TicketCommentSerializer, **STANDARD_ERRORS},
    )
    def post(self, request, ticket_id):
        ticket = self._get_ticket(request, ticket_id)
        if ticket is None:
            return _error("ticket_not_found", "Ticket not found", status.HTTP_404_NOT_FOUND)

        payload = request.data or {}
        raw_content = payload.get("content") or ""
        content = str(raw_content).strip()
        if not content:
            return _error("invalid_request", "content is required", status.HTTP_400_BAD_REQUEST)

        comment = TicketComment.objects.create(
            ticket=ticket,
            author=request.user,
            content=content,
        )
        return Response(self._serialize_comment(comment), status=status.HTTP_201_CREATED)


class TicketSummaryView(TicketAPIMixin, ProtectedAPIView):
    """Get ticket statistics/summary."""

    OPEN_STATUSES = ["O", "A", "I", "W", "P"]
    CLOSED_STATUSES = ["C"]

    @extend_schema(
        summary="Get ticket summary",
        description="Get aggregated ticket statistics: total, open, and closed counts.",
        tags=[Tags.CRM_TICKETS],
        responses={200: TicketSummaryResponseSerializer, **STANDARD_ERRORS},
    )
    def get(self, request):
        tenant = getattr(request.user, "tenant", None)
        if tenant is None:
            return Response({"total": 0, "open": 0, "closed": 0})

        queryset = self._tenant_queryset(request)
        counts = queryset.aggregate(
            total=Count("id"),
            open=Count("id", filter=Q(status__in=self.OPEN_STATUSES)),
            closed=Count("id", filter=Q(status__in=self.CLOSED_STATUSES)),
        )
        return Response({
            "total": counts.get("total", 0) or 0,
            "open": counts.get("open", 0) or 0,
            "closed": counts.get("closed", 0) or 0,
        })

