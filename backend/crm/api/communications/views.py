from __future__ import annotations

from typing import Any, Dict, Optional

from django.db.models import Count, Max, OuterRef, Q, Subquery
from django.utils import timezone
from django.utils.text import slugify
from drf_spectacular.utils import extend_schema, OpenApiParameter, OpenApiResponse
from drf_spectacular.types import OpenApiTypes
from rest_framework import status
from rest_framework.response import Response

from crm.api.mixins import CommunicationsAPIMixin, ProtectedAPIView, _error
from crm.models import Contact
from chatbot.models.agent_session import AgentSession


@extend_schema(tags=["communications"])
class CommunicationsConversationsView(ProtectedAPIView, CommunicationsAPIMixin):
    @extend_schema(summary="List conversations", parameters=[OpenApiParameter("search", OpenApiTypes.STR), OpenApiParameter("channel", OpenApiTypes.STR), OpenApiParameter("status", OpenApiTypes.STR), OpenApiParameter("contact_id", OpenApiTypes.UUID), OpenApiParameter("include_messages", OpenApiTypes.BOOL), OpenApiParameter("page", OpenApiTypes.INT), OpenApiParameter("page_size", OpenApiTypes.INT)], responses={200: OpenApiResponse(description="conversations, pagination, optional messages")})
    def get(self, request):
        tenant_sessions = self._tenant_sessions_queryset(request)

        search = request.query_params.get("search")
        channel_filter = request.query_params.get("channel")
        status_filter = request.query_params.get("status")
        contact_id = request.query_params.get("contact_id")
        include_messages = self._parse_bool(request.query_params.get("include_messages"))

        queryset = tenant_sessions
        if channel_filter:
            queryset = queryset.filter(channel__iexact=channel_filter)
        if status_filter:
            if status_filter == "active":
                queryset = queryset.filter(active=True)
            elif status_filter == "closed":
                queryset = queryset.filter(active=False, end__isnull=False)
            elif status_filter == "pending":
                queryset = queryset.filter(active=False, end__isnull=True)
        if contact_id:
            queryset = queryset.filter(contact_id=contact_id)

        if search:
            queryset = queryset.filter(
                Q(contact__fullname__icontains=search)
                | Q(contact__phone__icontains=search)
                | Q(contact__email__icontains=search)
            )

        latest_messages = Subquery(
            tenant_sessions.filter(pk=OuterRef("pk"))
            .annotate(latest=Max("threads__created"))
            .values("latest")[:1]
        )

        queryset = queryset.annotate(last_message_at=latest_messages)

        page_size = self._parse_int(
            request.query_params.get("page_size"), default=self.DEFAULT_PAGE_SIZE, max_value=self.MAX_PAGE_SIZE
        )
        page = self._parse_int(request.query_params.get("page"), default=1)
        offset = (page - 1) * page_size
        total = queryset.count()

        sessions = list(queryset.order_by("-last_message_at", "-updated")[offset : offset + page_size])

        def _serialize(session):
            contact = session.contact
            return {
                "id": str(session.id),
                "contact": self._serialize_contact(contact, request),
                "channel": session.channel or "unknown",
                "status": self._conversation_status(session),
                "unread_messages": self._unread_count(session),
                "tags": self._conversation_tags(contact),
                "assigned_to": None,
                "start": self._isoformat(session.start),
                "end": self._isoformat(session.end),
                "last_interaction": self._isoformat(session.last_interaction),
                "started_by": session.started_by,
                "context": session.context or {},
                "final_summary": session.final_summary,
                "active": session.active,
                "busy": session.busy,
                "human_mode": session.human_mode,
                "csat": session.csat,
                "created_at": self._isoformat(session.created),
                "updated_at": self._isoformat(session.updated),
            }

        payload = {
            "conversations": [_serialize(session) for session in sessions],
            "pagination": {
                "total": total,
                "page": page,
                "page_size": page_size,
            },
        }

        if include_messages:
            payload["messages"] = {
                str(session.id): [
                    self._serialize_message(message, session.contact)
                    for message in getattr(session, "prefetched_messages", [])
                ]
                for session in sessions
            }

        return Response(payload)

    @extend_schema(summary="Create conversation", description="Body: contact_id (required), channel, started_by, context", responses={201: OpenApiResponse(description="conversation")})
    def post(self, request):
        tenant = getattr(request.user, "tenant", None)
        if tenant is None:
            return _error("tenant_not_found", "User is not associated with a tenant", status.HTTP_403_FORBIDDEN)

        contact_id = request.data.get("contact_id")
        channel = request.data.get("channel", "web")
        started_by = request.data.get("started_by")
        context = request.data.get("context") or {}

        if not contact_id:
            return _error("missing_field", "contact_id is required", status.HTTP_400_BAD_REQUEST)

        try:
            contact = Contact.objects.get(id=contact_id, tenant=tenant)
        except Contact.DoesNotExist:
            return _error("contact_not_found", "Contact not found", status.HTTP_404_NOT_FOUND)

        now = timezone.now()
        session = AgentSession.objects.create(
            tenant=tenant,
            contact=contact,
            channel=channel,
            started_by=started_by,
            context=context,
            start=now,
            active=True,
        )

        return Response(
            {
                "id": str(session.id),
                "contact": self._serialize_contact(contact, request),
                "channel": session.channel,
                "status": "active",
                "start": self._isoformat(session.start),
                "end": None,
                "last_interaction": self._isoformat(session.last_interaction),
                "started_by": session.started_by,
                "context": session.context or {},
                "final_summary": session.final_summary,
                "active": session.active,
                "busy": session.busy,
                "human_mode": session.human_mode,
                "csat": session.csat,
                "created_at": self._isoformat(session.created),
                "updated_at": self._isoformat(session.updated),
            },
            status=status.HTTP_201_CREATED,
        )


@extend_schema(tags=["communications"])
class CommunicationsConversationDetailView(ProtectedAPIView, CommunicationsAPIMixin):
    @extend_schema(summary="Get conversation", responses={200: OpenApiResponse(description="conversation with messages")})
    def get(self, request, session_id: str):
        session = self._get_session_for_request(request, session_id)
        if session is None:
            return _error("conversation_not_found", "Conversation not found", status.HTTP_404_NOT_FOUND)
        contact = session.contact
        payload = {
            "id": str(session.id),
            "contact": self._serialize_contact(contact, request),
            "channel": session.channel or "unknown",
            "status": self._conversation_status(session),
            "unread_messages": self._unread_count(session),
            "tags": self._conversation_tags(contact),
            "assigned_to": None,
            "start": self._isoformat(session.start),
            "end": self._isoformat(session.end),
            "last_interaction": self._isoformat(session.last_interaction),
            "started_by": session.started_by,
            "context": session.context or {},
            "final_summary": session.final_summary,
            "active": session.active,
            "busy": session.busy,
            "human_mode": session.human_mode,
            "csat": session.csat,
            "created_at": self._isoformat(session.created),
            "updated_at": self._isoformat(session.updated),
            "messages": [self._serialize_message(message, contact) for message in session.prefetched_messages],
        }
        return Response(payload)

    @extend_schema(summary="Update conversation", description="Body: end_conversation, human_mode, final_summary, csat", responses={200: OpenApiResponse(description="conversation")})
    def patch(self, request, session_id: str):
        session = self._get_session_for_request(request, session_id)
        if session is None:
            return _error("conversation_not_found", "Conversation not found", status.HTTP_404_NOT_FOUND)

        # Handle end conversation
        if request.data.get("end_conversation"):
            session.end = timezone.now()
            session.active = False
            session.save()

        # Handle human mode toggle
        if "human_mode" in request.data:
            session.human_mode = self._parse_bool(request.data.get("human_mode"))
            session.save()

        # Handle final summary
        if "final_summary" in request.data:
            session.final_summary = request.data.get("final_summary")
            session.save()

        # Handle CSAT
        if "csat" in request.data:
            csat_val = request.data.get("csat")
            if csat_val is not None:
                try:
                    session.csat = int(csat_val)
                    session.save()
                except (ValueError, TypeError):
                    return _error("invalid_field", "csat must be an integer", status.HTTP_400_BAD_REQUEST)

        contact = session.contact
        return Response(
            {
                "id": str(session.id),
                "contact": self._serialize_contact(contact, request),
                "channel": session.channel or "unknown",
                "status": self._conversation_status(session),
                "unread_messages": self._unread_count(session),
                "tags": self._conversation_tags(contact),
                "assigned_to": None,
                "start": self._isoformat(session.start),
                "end": self._isoformat(session.end),
                "last_interaction": self._isoformat(session.last_interaction),
                "started_by": session.started_by,
                "context": session.context or {},
                "final_summary": session.final_summary,
                "active": session.active,
                "busy": session.busy,
                "human_mode": session.human_mode,
                "csat": session.csat,
                "created_at": self._isoformat(session.created),
                "updated_at": self._isoformat(session.updated),
            }
        )


@extend_schema(tags=["communications"])
class CommunicationsConversationMessagesView(ProtectedAPIView, CommunicationsAPIMixin):
    @extend_schema(summary="List conversation messages", parameters=[OpenApiParameter("page", OpenApiTypes.INT), OpenApiParameter("page_size", OpenApiTypes.INT)], responses={200: OpenApiResponse(description="messages, pagination")})
    def get(self, request, session_id: str):
        session = self._get_session_for_request(request, session_id)
        if session is None:
            return _error("conversation_not_found", "Conversation not found", status.HTTP_404_NOT_FOUND)

        contact = session.contact
        page_size = self._parse_int(
            request.query_params.get("page_size"), default=self.DEFAULT_PAGE_SIZE, max_value=self.MAX_PAGE_SIZE
        )
        page = self._parse_int(request.query_params.get("page"), default=1)
        offset = (page - 1) * page_size
        messages_qs = session.threads.order_by("-created")
        total = messages_qs.count()
        messages = list(messages_qs[offset : offset + page_size])
        payload = {
            "messages": [self._serialize_message(message, contact) for message in messages],
            "pagination": {
                "total": total,
                "page": page,
                "page_size": page_size,
            },
        }
        return Response(payload)


@extend_schema(tags=["communications"])
class CommunicationsConversationMarkReadView(ProtectedAPIView, CommunicationsAPIMixin):
    @extend_schema(summary="Mark conversation as read", responses={200: OpenApiResponse(description="conversation_id, unread_count, marked_at")})
    def patch(self, request, session_id: str):
        session = self._get_session_for_request(request, session_id)
        if session is None:
            return _error("conversation_not_found", "Conversation not found", status.HTTP_404_NOT_FOUND)

        latest_user_message = (
            session.threads.filter(role__iexact="USER").order_by("-created").first()
        )
        now = timezone.now()
        context = dict(session.context or {})
        if latest_user_message:
            context["last_read_at"] = self._isoformat(latest_user_message.created)
            context["last_read_message_id"] = str(latest_user_message.id)
        else:
            context["last_read_at"] = self._isoformat(now)
            context.pop("last_read_message_id", None)
        session.context = context
        session.save(update_fields=["context"])

        unread_count = self._unread_count(session)

        return Response(
            {
                "conversation_id": str(session.pk),
                "unread_count": unread_count,
                "marked_at": self._isoformat(now),
                "last_read_message_id": context.get("last_read_message_id"),
            }
        )


@extend_schema(tags=["communications"])
class CommunicationsChannelsView(ProtectedAPIView, CommunicationsAPIMixin):
    @extend_schema(summary="List channels", responses={200: OpenApiResponse(description="channels")})
    def get(self, request):
        channels = []
        tenant_sessions = self._tenant_sessions_queryset(request)
        distinct_channels = tenant_sessions.values_list("channel", flat=True).distinct()
        for channel_name in distinct_channels:
            channel_key = slugify(channel_name) or "channel"
            channels.append(
                {
                    "id": channel_key,
                    "name": channel_name or "Unknown",
                    "type": channel_key,
                    "capabilities": self._channel_capabilities(channel_key),
                }
            )
        return Response({"channels": channels})

