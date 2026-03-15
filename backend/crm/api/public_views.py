from __future__ import annotations

import logging
import re
import uuid
from datetime import datetime, timezone as dt_timezone
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# Contact.phone max length (must match crm.models.Contact.phone)
CONTACT_PHONE_MAX_LENGTH = 15
_NON_DIALABLE_RE = re.compile(r"[^\d+]+")

from django.core.paginator import Paginator
from django.db import connection
from django.db.utils import DataError, IntegrityError
from django.db.models import Count, DateTimeField, F, Max, OuterRef, Q, Subquery, Prefetch, Sum, Value
from django.db.models.fields.json import KeyTextTransform
from django.db.models.functions import Cast, Coalesce
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.utils.text import slugify
from django.views.decorators.csrf import csrf_exempt
from rest_framework import serializers, status
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.authentication import JWTAuthentication
from drf_spectacular.utils import extend_schema

from moio_platform.authentication import BearerTokenAuthentication
from central_hub.authentication import CsrfExemptSessionAuthentication, TenantJWTAAuthentication, UserApiKeyAuthentication
from tenancy.resolution import _current_connection_schema

_tenancy_trace = logging.getLogger("tenancy_trace")

from crm.models import Contact, ContactType, Ticket, TicketComment, Customer, CustomerContact
from crm.services.contact import normalize_phone_e164, sync_whatsapp_blocklist
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer

from chatbot.models.agent_session import AgentSession, SessionThread
from chatbot.models.agent_configuration import CHANNEL_SHOPIFY_WEBCHAT
from chatbot.core.human_mode_context import append_context_message

from .data_store import demo_store
from crm.services.ticket_service import TicketService
from crm.api.mixins import ProtectedAPIView, TicketAPIMixin


_UNSET = object()


def _error(code: str, message: str, http_status: int = status.HTTP_400_BAD_REQUEST) -> Response:
    return Response({"error": code, "message": message}, status=http_status)


def _normalize_and_validate_phone(raw_phone: str) -> Tuple[str, Optional[Response]]:
    """
    Normalize phone (strip, remove spaces; E.164 when possible) and validate length.
    Returns (normalized_value, None) or ("", error_response) for 400.
    """
    raw = (raw_phone or "").strip()
    if not raw:
        return "", None
    normalized = normalize_phone_e164(raw)
    if normalized is None:
        # Fallback: strip non-dialable chars so "+598 95 750 350" -> "+59895750350"
        normalized = _NON_DIALABLE_RE.sub("", raw)
        if normalized.startswith("00"):
            normalized = "+" + normalized[2:]
        elif normalized and not normalized.startswith("+") and normalized.isdigit():
            normalized = "+" + normalized
    if len(normalized) > CONTACT_PHONE_MAX_LENGTH:
        return "", Response(
            {
                "error": "invalid_request",
                "message": f"Phone must be at most {CONTACT_PHONE_MAX_LENGTH} characters after normalization.",
                "details": {"phone": [f"Ensure this field has no more than {CONTACT_PHONE_MAX_LENGTH} characters (it has {len(normalized)})."]},
            },
            status=status.HTTP_400_BAD_REQUEST,
        )
    return normalized or "", None


class CommunicationsAPIMixin:
    DEFAULT_PAGE_SIZE = 25
    MAX_PAGE_SIZE = 100

    def _resolve_tenant_for_request(self, request):
        """Tenant is set by TenantAndRLSMiddleware."""
        return getattr(request, "tenant", None) or getattr(request.user, "tenant", None)

    def _get_tenant_or_none(self, request):
        return self._resolve_tenant_for_request(request)

    def _ensure_tenant_schema(self, request):
        """No-op: TenantAndRLSMiddleware sets request.tenant and app.current_tenant_slug."""
        pass

    def _isoformat(self, dt: Optional[timezone.datetime]) -> Optional[str]:
        if not dt:
            return None
        return (
            dt.astimezone(dt_timezone.utc)
            .replace(microsecond=0)
            .isoformat()
            .replace("+00:00", "Z")
        )

    def _parse_iso_datetime(self, raw_value: Optional[str]) -> Optional[timezone.datetime]:
        if not raw_value:
            return None
        try:
            normalized = raw_value
            if normalized.endswith("Z"):
                normalized = normalized[:-1] + "+00:00"
            parsed = datetime.fromisoformat(normalized)
        except ValueError:
            return None
        if timezone.is_naive(parsed):
            return timezone.make_aware(parsed, timezone=dt_timezone.utc)
        return parsed

    def _tenant_sessions_queryset(self, request):
        self._ensure_tenant_schema(request)
        tenant = self._get_tenant_or_none(request)
        if tenant is None:
            return AgentSession.objects.none()
        base_qs = AgentSession.objects.filter(tenant=tenant).select_related("contact", "contact__ctype")
        messages_prefetch = Prefetch(
            "threads",
            queryset=SessionThread.objects.order_by("-created")[:50],
            to_attr="prefetched_messages",
        )
        return base_qs.prefetch_related(messages_prefetch)

    def _parse_bool(self, value: Optional[str]) -> bool:
        if value is None:
            return False
        if isinstance(value, bool):
            return value
        normalized = str(value).strip().lower()
        return normalized in {"1", "true", "yes", "on"}

    def _parse_int(self, value: Optional[str], *, default: int, max_value: Optional[int] = None, min_value: int = 1) -> int:
        try:
            parsed = int(value)
        except (TypeError, ValueError):
            parsed = default
        parsed = max(min_value, parsed)
        if max_value is not None:
            parsed = min(max_value, parsed)
        return parsed

    def _serialize_contact(self, contact: Contact, request) -> Dict[str, Optional[str]]:
        display_name = (
            contact.display_name
            or contact.fullname
            or contact.whatsapp_name
            or contact.first_name
            or contact.phone
            or contact.mobile
            or ""
        )
        avatar_url = None
        if contact.image:
            try:
                avatar_url = request.build_absolute_uri(contact.image.url)
            except Exception:  # pragma: no cover - fallback for storage backends without request
                avatar_url = contact.image.url
        ctype = getattr(contact, "ctype", None)
        return {
            "id": str(contact.user_id),
            "name": display_name,
            "phone": contact.phone or contact.mobile or "",
            "email": contact.email or "",
            "avatar_url": avatar_url,
            "contacttype": {
                "id": str(ctype.pk) if ctype else None,
                "name": ctype.name if ctype else None,
            } if ctype else None,
        }

    def _sender_from_role(self, role: Optional[str]) -> str:
        if not role:
            return "system"
        normalized = role.lower()
        if normalized == "user":
            return "contact"
        if normalized == "assistant":
            return "agent"
        return "system"

    def _serialize_message(self, message: SessionThread, contact: Contact) -> Dict[str, Any]:
        sender = self._sender_from_role(message.role)
        sender_name = contact.display_name or contact.fullname or contact.whatsapp_name or contact.phone or contact.mobile
        if sender == "agent":
            sender_name = message.author or "Moio Agent"
        elif sender == "system":
            sender_name = message.author or "System"
        return {
            "id": str(message.id),
            "conversation_id": str(message.session_id),
            "content": message.content,
            "sender": sender,
            "sender_name": sender_name or "",
            "timestamp": self._isoformat(message.created),
            "status": "delivered" if sender == "contact" else "sent",
            "type": "text",
            "attachments": [],
        }

    def _conversation_tags(self, contact: Contact) -> List[str]:
        facts = contact.brief_facts or {}
        tags = facts.get("tags")
        if isinstance(tags, list):
            return [str(tag) for tag in tags if tag]
        return []

    def _channel_capabilities(self, channel: Optional[str]) -> List[str]:
        channel_key = (channel or "").lower()
        if channel_key == "email":
            return ["text", "html", "attachments"]
        if channel_key in {"sms", "texto"}:
            return ["text"]
        if channel_key in {"instagram", "telegram", "messenger"}:
            return ["text", "image", "video", "audio", "document"]
        # default to WhatsApp-style rich messaging
        return ["text", "image", "video", "audio", "document", "location"]

    def _conversation_status(self, session: AgentSession) -> str:
        if session.active:
            return "active"
        if session.end:
            return "closed"
        return "pending"

    def _get_last_message(self, session: AgentSession) -> Optional[SessionThread]:
        messages = getattr(session, "prefetched_messages", None)
        if messages:
            return messages[0]
        return session.threads.order_by("-created").first()

    def _get_session_for_request(self, request, session_id: str) -> Optional[AgentSession]:
        queryset = self._tenant_sessions_queryset(request)
        try:
            return queryset.get(pk=session_id)
        except AgentSession.DoesNotExist:
            return None

    def _unread_count(self, session: AgentSession) -> int:
        context = session.context or {}
        last_read_at_raw = context.get("last_read_at") if isinstance(context, dict) else None
        last_read_at = self._parse_iso_datetime(last_read_at_raw)
        qs = session.threads.filter(role__iexact="USER")
        if last_read_at:
            qs = qs.filter(created__gt=last_read_at)
        return qs.count()

    def _serialize_conversation_summary(self, request, session: AgentSession) -> Dict[str, Any]:
        last_message = self._get_last_message(session)
        contact_payload = self._serialize_contact(session.contact, request)
        unread_count = self._unread_count(session)
        updated_at = (
            last_message.created
            if last_message is not None
            else session.last_interaction or session.start
        )
        payload: Dict[str, Any] = {
            "id": str(session.pk),
            "contact": contact_payload,
            "channel": session.channel or "unknown",
            "status": self._conversation_status(session),
            "unread_count": unread_count,
            "updated_at": self._isoformat(updated_at),
            "tags": self._conversation_tags(session.contact),
        }
        if last_message:
            payload["last_message"] = self._serialize_message(last_message, session.contact)
        else:
            payload["last_message"] = None
        return payload

    def _serialize_session_with_metadata(self, request, session: AgentSession) -> Dict[str, Any]:
        updated_source = session.last_interaction or session.end or session.start
        return {
            "id": str(session.pk),
            "contact": self._serialize_contact(session.contact, request),
            "channel": session.channel or "unknown",
            "status": self._conversation_status(session),
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
            "created_at": self._isoformat(session.start),
            "updated_at": self._isoformat(updated_source),
            "metadata": {
                "total_messages": session.threads.count(),
                "ai_summary": session.final_summary or "",
            },
            "unread_count": self._unread_count(session),
            "tags": self._conversation_tags(session.contact),
        }


from crm.api.contacts import views as contact_views

ContactDetailView = contact_views.ContactDetailView
ContactExportView = contact_views.ContactExportView
ContactsSummaryView = contact_views.ContactsSummaryView
ContactsView = contact_views.ContactsView


@method_decorator(csrf_exempt, name="dispatch")
@extend_schema(tags=["deals"])
class DealsView(ProtectedAPIView):
    def get(self, request):
        deals = demo_store.list_deals()
        response = {
            "deals": deals,
            "pipelines": {
                "qualification": [deal for deal in deals if deal["stage"] == "qualification"],
                "proposal": [deal for deal in deals if deal["stage"] == "proposal"],
                "negotiation": [deal for deal in deals if deal["stage"] == "negotiation"],
                "won": [deal for deal in deals if deal["stage"] == "won"],
            },
            "count": len(deals),
        }
        return Response(response)

    def post(self, request):
        deal = demo_store.create_deal(request.data or {})
        return Response(deal, status=status.HTTP_201_CREATED)


@method_decorator(csrf_exempt, name="dispatch")
@extend_schema(tags=["campaigns"])
class CampaignListView(ProtectedAPIView):
    def get(self, request):
        campaigns = demo_store.list_campaigns()
        return Response({"campaigns": campaigns, "pagination": {"current_page": 1, "total_pages": 1, "total_items": len(campaigns)}})

    def post(self, request):
        if not request.data.get("name"):
            return _error("invalid_request", "name is required", status.HTTP_400_BAD_REQUEST)
        campaign = demo_store.create_campaign(request.data)
        return Response(campaign, status=status.HTTP_201_CREATED)


@extend_schema(tags=["templates"])
class TemplateListView(ProtectedAPIView):
    def get(self, request):
        return Response({"templates": demo_store.list_templates()})


@method_decorator(csrf_exempt, name="dispatch")
@extend_schema(tags=["flows"])
class FlowListView(ProtectedAPIView):
    def get(self, request):
        flows = demo_store.list_flows()
        return Response({"flows": flows, "count": len(flows)})

    def post(self, request):
        if not request.data.get("name"):
            return _error("invalid_request", "name is required", status.HTTP_400_BAD_REQUEST)
        flow = demo_store.create_flow(request.data)
        return Response(flow, status=status.HTTP_201_CREATED)

@method_decorator(csrf_exempt, name="dispatch")
@extend_schema(tags=["flows"])
class FlowRunsView(ProtectedAPIView):
    def get(self, request):
        runs = demo_store.list_flow_runs()
        return Response({"runs": runs, "count": len(runs)})


@method_decorator(csrf_exempt, name="dispatch")
@extend_schema(tags=["communications"])
class CommunicationsConversationsView(ProtectedAPIView, CommunicationsAPIMixin):
    def get(self, request):
        queryset = self._tenant_sessions_queryset(request)
        latest_created_subquery = (
            SessionThread.objects.filter(session=OuterRef("pk"))
            .order_by("-created")
            .values("created")[:1]
        )
        latest_role_subquery = (
            SessionThread.objects.filter(session=OuterRef("pk"))
            .order_by("-created")
            .values("role")[:1]
        )
        queryset = queryset.annotate(
            latest_message_created=Coalesce(
                Subquery(latest_created_subquery),
                "last_interaction",
                "start",
            ),
            latest_message_role=Subquery(latest_role_subquery),
        )

        channel_filter = request.query_params.get("channel")
        if channel_filter:
            queryset = queryset.filter(channel__iexact=channel_filter)

        search_term = request.query_params.get("search")
        if search_term:
            queryset = queryset.filter(
                Q(contact__fullname__icontains=search_term)
                | Q(contact__display_name__icontains=search_term)
                | Q(contact__phone__icontains=search_term)
                | Q(contact__mobile__icontains=search_term)
            )

        if self._parse_bool(request.query_params.get("unread_only")):
            queryset = queryset.filter(latest_message_role__iexact="USER")

        page_number = self._parse_int(request.query_params.get("page"), default=1)
        page_size = self._parse_int(
            request.query_params.get("limit"),
            default=self.DEFAULT_PAGE_SIZE,
            max_value=self.MAX_PAGE_SIZE,
        )

        queryset = queryset.order_by("-latest_message_created", "-last_interaction", "-start")
        paginator = Paginator(queryset, page_size)
        page_obj = paginator.get_page(page_number)

        conversations = [
            self._serialize_conversation_summary(request, session)
            for session in page_obj.object_list
        ]

        pagination = {
            "current_page": page_obj.number,
            "total_pages": paginator.num_pages or 1,
            "total_items": paginator.count,
        }

        return Response({"conversations": conversations, "pagination": pagination})

    def post(self, request):
        tenant = self._get_tenant_or_none(request)
        if tenant is None:
            return _error("tenant_not_configured", "User is not associated with a tenant")

        contact_id = request.data.get("contact_id")
        channel = request.data.get("channel", "web")

        if not contact_id:
            return _error("invalid_request", "contact_id is required")

        try:
            contact = Contact.objects.get(pk=contact_id, tenant=tenant)
        except Contact.DoesNotExist:
            return _error("contact_not_found", "Contact not found", status.HTTP_404_NOT_FOUND)

        now = timezone.now()
        session_context = request.data.get("context") or {"created_via_api": True}
        session = AgentSession.objects.create(
            tenant=tenant,
            contact=contact,
            start=now,
            last_interaction=now,
            channel=channel,
            started_by=request.data.get("started_by") or getattr(request.user, "email", "api"),
            context=session_context,
            active=True,
        )

        return Response(
            self._serialize_session_with_metadata(request, session),
            status=status.HTTP_201_CREATED,
        )

@method_decorator(csrf_exempt, name="dispatch")
@extend_schema(tags=["communications"])
class CommunicationsConversationDetailView(ProtectedAPIView, CommunicationsAPIMixin):
    def get(self, request, session_id: str):
        session = self._get_session_for_request(request, session_id)
        if session is None:
            return _error("not_found", "Conversation not found", status.HTTP_404_NOT_FOUND)

        limit = self._parse_int(
            request.query_params.get("limit"), default=50, max_value=self.MAX_PAGE_SIZE
        )
        before_raw = request.query_params.get("before")
        before_dt = self._parse_iso_datetime(before_raw)
        if before_raw and before_dt is None:
            return _error("invalid_request", "before must be an ISO-8601 timestamp")

        messages_qs = session.threads.order_by("-created")
        if before_dt:
            messages_qs = messages_qs.filter(created__lt=before_dt)
        messages = list(messages_qs[:limit])
        messages.reverse()

        payload = self._serialize_session_with_metadata(request, session)
        payload["messages"] = [self._serialize_message(message, session.contact) for message in messages]

        return Response(payload)

    def patch(self, request, session_id: str):
        session = self._get_session_for_request(request, session_id)
        if session is None:
            return _error("not_found", "Conversation not found", status.HTTP_404_NOT_FOUND)

        if request.data.get("end_conversation"):
            session.end = timezone.now()
            session.active = False

        if "human_mode" in request.data:
            session.human_mode = self._parse_bool(request.data.get("human_mode"))

        if "final_summary" in request.data:
            session.final_summary = request.data.get("final_summary")

        if "csat" in request.data:
            csat_val = request.data.get("csat")
            if csat_val is not None:
                try:
                    session.csat = int(csat_val)
                except (ValueError, TypeError):
                    return _error("invalid_field", "csat must be an integer", status.HTTP_400_BAD_REQUEST)

        session.save()
        return Response(self._serialize_session_with_metadata(request, session))

@method_decorator(csrf_exempt, name="dispatch")
@extend_schema(tags=["communications"])
class CommunicationsConversationMessagesView(ProtectedAPIView, CommunicationsAPIMixin):
    def post(self, request, session_id: str):
        session = self._get_session_for_request(request, session_id)
        if session is None:
            return _error("not_found", "Conversation not found", status.HTTP_404_NOT_FOUND)

        nested_message = request.data.get("message")
        if nested_message and not isinstance(nested_message, dict):
            return _error("invalid_request", "message must be an object")
        content = request.data.get("content")
        if not content and nested_message:
            content = nested_message.get("content")
        if not content:
            return _error("invalid_request", "content is required")
        if session.human_mode and isinstance(content, list):
            return _error("invalid_request", "content must be a string in human mode")
        if isinstance(content, list):
            if any(not isinstance(item, str) for item in content):
                return _error("invalid_request", "content list items must be strings")
        elif not isinstance(content, str):
            return _error("invalid_request", "content must be a string or list")

        author_name = getattr(request.user, "get_full_name", lambda: "")() or getattr(
            request.user, "email", ""
        ) or getattr(request.user, "username", "")

        # Check if human mode is enabled
        if session.human_mode:
            # Shopify webchat: persist and push via WebSocket so widget shows it in real time
            if session.channel == CHANNEL_SHOPIFY_WEBCHAT:
                text_content = content if isinstance(content, str) else str(content)
                message = SessionThread.objects.create(
                    session=session,
                    role="ASSISTANT",
                    content=text_content,
                    author=author_name,
                )
                session.context = append_context_message(session.context, "assistant", text_content)
                session.last_interaction = timezone.now()
                session.active = True
                session.save(update_fields=["last_interaction", "active", "context"])
                try:
                    channel_layer = get_channel_layer()
                    if channel_layer:
                        group_name = f"shopify_chat_session_{session.pk}"
                        async_to_sync(channel_layer.group_send)(
                            group_name,
                            {
                                "type": "human_message",
                                "content": text_content,
                                "author": author_name,
                                "timestamp": timezone.now().isoformat(),
                            },
                        )
                except Exception as e:
                    logger.warning("Shopify webchat push human message via WebSocket failed: %s", e)
                return Response(
                    {
                        "conversation_id": str(session.pk),
                        "message": self._serialize_message(message, session.contact),
                    },
                    status=status.HTTP_201_CREATED,
                )
            try:
                from chatbot.core.messenger import Messenger
                from central_hub.tenant_config import get_tenant_config

                config = get_tenant_config(session.tenant)
                messenger = Messenger(channel=session.channel, config=config, client_name="human_mode")
                delivery_report = messenger.just_reply_with_report(content, session.contact.phone)
                send_success = bool(delivery_report.get("success", False))
                sent_items = delivery_report.get("sent_items") or []

                if not send_success or not sent_items:
                    return _error("send_failed", "Failed to send message to contact", status.HTTP_500_INTERNAL_SERVER_ERROR)

                delivered_content = sent_items[0]
                message = SessionThread.objects.create(
                    session=session,
                    role="ASSISTANT",
                    content=delivered_content,
                    author=author_name,
                )
                session.context = append_context_message(session.context, "assistant", delivered_content)

                session.last_interaction = timezone.now()
                session.active = True
                session.save(update_fields=["last_interaction", "active", "context"])

                return Response(
                    {
                        "conversation_id": str(session.pk),
                        "message": self._serialize_message(message, session.contact),
                    },
                    status=status.HTTP_201_CREATED,
                )

            except Exception as e:
                logger.error(f"Error sending human mode message: {e}")
                return _error("send_error", "Error sending message", status.HTTP_500_INTERNAL_SERVER_ERROR)
        else:
            # Normal mode: Just add to conversation thread (existing behavior)
            message = SessionThread.objects.create(
                session=session,
                role="ASSISTANT",
                content=content,
                author=author_name,
            )

            session.last_interaction = timezone.now()
            session.active = True
            session.save(update_fields=["last_interaction", "active"])

            return Response(
                {
                    "conversation_id": str(session.pk),
                    "message": self._serialize_message(message, session.contact),
                },
                status=status.HTTP_201_CREATED,
            )

@method_decorator(csrf_exempt, name="dispatch")
@extend_schema(tags=["communications"])
class CommunicationsConversationMarkReadView(ProtectedAPIView, CommunicationsAPIMixin):
    def patch(self, request, session_id: str):
        session = self._get_session_for_request(request, session_id)
        if session is None:
            return _error("not_found", "Conversation not found", status.HTTP_404_NOT_FOUND)
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

@method_decorator(csrf_exempt, name="dispatch")
@extend_schema(tags=["communications"])
class CommunicationsChannelsView(ProtectedAPIView, CommunicationsAPIMixin):
    def get(self, request):
        queryset = self._tenant_sessions_queryset(request)
        channel_stats = (
            queryset.exclude(channel__isnull=True)
            .exclude(channel__exact="")
            .values("channel")
            .annotate(
                total_conversations=Count("pk"),
                active_conversations=Count("pk", filter=Q(active=True)),
                last_activity=Max(Coalesce("last_interaction", "start")),
            )
        )

        channels = []
        for entry in channel_stats:
            channel_name = entry["channel"]
            channels.append(
                {
                    "id": slugify(channel_name) or "channel",
                    "name": channel_name,
                    "type": channel_name,
                    "status": "active" if entry["active_conversations"] else "inactive",
                    "capabilities": self._channel_capabilities(channel_name),
                    "total_conversations": entry["total_conversations"],
                    "active_conversations": entry["active_conversations"],
                    "last_activity": self._isoformat(entry["last_activity"]),
                }
            )

        return Response({"channels": channels})


def _wa_log_consolidated_sql_and_params(tenant_id, start_dt=None, end_dt=None, flow_execution_id=None, limit=25, offset=0):
    """Build parameterized raw SQL for consolidated wa_message_log report. Returns (sql, params)."""
    base_where = "WHERE NULLIF(w.msg_id::text, '') IS NOT NULL AND w.tenant_id = %s"
    params = [tenant_id]
    if start_dt is not None:
        base_where += " AND COALESCE(w.\"timestamp\", w.updated, w.created) >= %s"
        params.append(start_dt)
    if end_dt is not None:
        base_where += " AND COALESCE(w.\"timestamp\", w.updated, w.created) <= %s"
        params.append(end_dt)
    if flow_execution_id is not None:
        base_where += " AND w.flow_execution_id = %s"
        params.append(flow_execution_id)

    sql = f"""
WITH base AS (
  SELECT
    w.tenant_id,
    NULLIF(w.msg_id::text, '')            AS msg_id,
    NULLIF(w.recipient_id::text, '')      AS recipient_id,
    NULLIF(w.flow_execution_id::text, '') AS flow_execution_id,
    NULLIF(w.status::text, '')            AS status,
    COALESCE(w."timestamp", w.updated, w.created) AS ts,
    (w.msg_content::jsonb ->> 'to')                       AS msg_to,
    (w.msg_content::jsonb ->> 'type')                     AS msg_type,
    (w.msg_content::jsonb #>> '{{template,name}}')          AS template_name,
    (w.msg_content::jsonb #>> '{{template,language,code}}') AS template_language_code,
    (w.msg_content::jsonb #>> '{{template,namespace}}')     AS template_namespace,
    (
      SELECT jsonb_object_agg(p->>'parameter_name', p->>'text')
      FROM jsonb_array_elements(COALESCE(w.msg_content::jsonb #> '{{template,components}}', '[]'::jsonb)) c
      CROSS JOIN LATERAL jsonb_array_elements(COALESCE(c->'parameters', '[]'::jsonb)) p
      WHERE c->>'type' = 'body' AND p ? 'parameter_name'
    ) AS template_body_params,
    (w.api_response::jsonb #>> '{{error,code}}')       AS api_error_code,
    (w.api_response::jsonb #>> '{{error,type}}')       AS api_error_type,
    (w.api_response::jsonb #>> '{{error,message}}')    AS api_error_message,
    (w.api_response::jsonb #>> '{{error,fbtrace_id}}') AS api_error_fbtrace_id,
    (w.api_response::jsonb #>> '{{error,error_data,details}}') AS api_error_details,
    (w.api_response::jsonb #>> '{{contacts,0,wa_id}}') AS api_wa_id,
    (w.api_response::jsonb #>> '{{messages,0,id}}')    AS api_message_wamid,
    (w.api_response::jsonb #>> '{{messages,0,message_status}}') AS api_message_status,
    CASE
      WHEN (w.api_response::jsonb #>> '{{error,code}}') IS NOT NULL
        THEN 'error:' || (w.api_response::jsonb #>> '{{error,code}}')
      WHEN (w.api_response::jsonb #>> '{{messages,0,message_status}}') IS NOT NULL
        THEN (w.api_response::jsonb #>> '{{messages,0,message_status}}')
      ELSE 'unknown'
    END AS result_val
  FROM wa_message_log w
  {base_where}
),
agg AS (
  SELECT
    tenant_id,
    msg_id,
    COALESCE(string_agg(DISTINCT recipient_id,      ' | ' ORDER BY recipient_id),      '-') AS recipient_id_all,
    COALESCE(string_agg(DISTINCT flow_execution_id, ' | ' ORDER BY flow_execution_id), '-') AS flow_execution_id_all,
    COALESCE(string_agg(DISTINCT msg_to,                 ' | ' ORDER BY msg_to), '-') AS msg_to_all,
    COALESCE(string_agg(DISTINCT msg_type,               ' | ' ORDER BY msg_type), '-') AS msg_type_all,
    COALESCE(string_agg(DISTINCT template_name,          ' | ' ORDER BY template_name), '-') AS template_name_all,
    COALESCE(string_agg(DISTINCT template_language_code, ' | ' ORDER BY template_language_code), '-') AS template_language_code_all,
    COALESCE(string_agg(DISTINCT template_namespace,     ' | ' ORDER BY template_namespace), '-') AS template_namespace_all,
    COALESCE(string_agg(DISTINCT template_body_params::text, ' | ' ORDER BY template_body_params::text), '-') AS template_body_params_all,
    COALESCE(string_agg(DISTINCT api_wa_id,          ' | ' ORDER BY api_wa_id), '-') AS api_wa_id_all,
    COALESCE(string_agg(DISTINCT api_message_wamid,  ' | ' ORDER BY api_message_wamid), '-') AS api_message_wamid_all,
    COALESCE(string_agg(DISTINCT api_message_status, ' | ' ORDER BY api_message_status), '-') AS api_message_status_all,
    COALESCE(string_agg(DISTINCT api_error_code,      ' | ' ORDER BY api_error_code), '-') AS api_error_code_all,
    COALESCE(string_agg(DISTINCT api_error_type,      ' | ' ORDER BY api_error_type), '-') AS api_error_type_all,
    COALESCE(string_agg(DISTINCT api_error_message,   ' | ' ORDER BY api_error_message), '-') AS api_error_message_all,
    COALESCE(string_agg(DISTINCT api_error_fbtrace_id, ' | ' ORDER BY api_error_fbtrace_id), '-') AS api_error_fbtrace_id_all,
    COALESCE(string_agg(DISTINCT api_error_details,   ' | ' ORDER BY api_error_details), '-') AS api_error_details_all,
    COALESCE(string_agg(DISTINCT result_val, ' | ' ORDER BY result_val), '-') AS result_all,
    MAX(ts) FILTER (WHERE status = 'accepted')  AS accepted_ts,
    MAX(ts) FILTER (WHERE status = 'sent')      AS sent_ts,
    MAX(ts) FILTER (WHERE status = 'delivered') AS delivered_ts,
    MAX(ts) FILTER (WHERE status = 'read')      AS read_ts,
    MAX(ts) FILTER (WHERE status = 'failed')    AS failed_ts,
    COUNT(*) AS row_count,
    COUNT(DISTINCT recipient_id) FILTER (WHERE recipient_id IS NOT NULL) AS recipient_id_variants,
    COUNT(DISTINCT flow_execution_id) FILTER (WHERE flow_execution_id IS NOT NULL) AS flow_execution_id_variants
  FROM base
  GROUP BY tenant_id, msg_id
)
SELECT
  tenant_id,
  msg_id,
  recipient_id_all      AS recipient_id,
  flow_execution_id_all AS flow_execution_id,
  msg_to_all                 AS msg_to,
  msg_type_all               AS msg_type,
  template_name_all          AS template_name,
  template_language_code_all AS template_language_code,
  template_namespace_all     AS template_namespace,
  template_body_params_all   AS template_body_params,
  result_all AS result,
  api_wa_id_all          AS api_wa_id,
  api_message_wamid_all  AS api_message_wamid,
  api_message_status_all AS api_message_status,
  api_error_code_all       AS api_error_code,
  api_error_type_all       AS api_error_type,
  api_error_message_all    AS api_error_message,
  api_error_fbtrace_id_all AS api_error_fbtrace_id,
  api_error_details_all    AS api_error_details,
  COALESCE(to_char(accepted_ts,  'YYYY-MM-DD HH24:MI:SSOF'), '-') AS accepted_at,
  COALESCE(to_char(sent_ts,      'YYYY-MM-DD HH24:MI:SSOF'), '-') AS sent_at,
  COALESCE(to_char(delivered_ts, 'YYYY-MM-DD HH24:MI:SSOF'), '-') AS delivered_at,
  COALESCE(to_char(read_ts,      'YYYY-MM-DD HH24:MI:SSOF'), '-') AS read_at,
  COALESCE(to_char(failed_ts,    'YYYY-MM-DD HH24:MI:SSOF'), '-') AS failed_at,
  row_count,
  recipient_id_variants,
  flow_execution_id_variants,
  COUNT(*) OVER () AS total_count
FROM agg
ORDER BY
  tenant_id,
  LEAST(
    COALESCE(accepted_ts,  'infinity'::timestamptz),
    COALESCE(sent_ts,      'infinity'::timestamptz),
    COALESCE(delivered_ts, 'infinity'::timestamptz),
    COALESCE(read_ts,      'infinity'::timestamptz),
    COALESCE(failed_ts,    'infinity'::timestamptz)
  ),
  msg_id
LIMIT %s OFFSET %s
"""
    params.extend([limit, offset])
    return sql, params


def _dictfetchall(cursor):
    columns = [col[0] for col in cursor.description]
    return [dict(zip(columns, row)) for row in cursor.fetchall()]


@method_decorator(csrf_exempt, name="dispatch")
@extend_schema(tags=["communications"])
class CommunicationsWhatsappLogsView(ProtectedAPIView, CommunicationsAPIMixin):
    """
    Tenant-scoped, consolidated WhatsApp delivery logs (report format).

    Returns one row per msg_id with aggregated template, API response, and status timestamps.

    Query params: page (default 1), limit (default 25, max 100), start, end (ISO or YYYY-MM-DD),
    flow_execution_id (UUID).
    """

    def get(self, request):
        tenant = self._get_tenant_or_none(request)
        if tenant is None:
            return _error("tenant_not_configured", "User is not associated with a tenant")

        start_raw = request.query_params.get("start")
        end_raw = request.query_params.get("end")
        if start_raw and len(start_raw) == 10:
            start_raw = f"{start_raw}T00:00:00Z"
        if end_raw and len(end_raw) == 10:
            end_raw = f"{end_raw}T23:59:59Z"
        start_dt = self._parse_iso_datetime(start_raw)
        end_dt = self._parse_iso_datetime(end_raw)
        if start_raw and start_dt is None:
            return _error("invalid_request", "start must be an ISO-8601 timestamp or YYYY-MM-DD")
        if end_raw and end_dt is None:
            return _error("invalid_request", "end must be an ISO-8601 timestamp or YYYY-MM-DD")

        flow_execution_id_raw = request.query_params.get("flow_execution_id")
        flow_execution_id = None
        if flow_execution_id_raw:
            try:
                flow_execution_id = uuid.UUID(str(flow_execution_id_raw))
            except (ValueError, TypeError):
                return _error("invalid_request", "flow_execution_id must be a UUID")

        page_number = self._parse_int(request.query_params.get("page"), default=1)
        page_size = self._parse_int(
            request.query_params.get("limit"),
            default=self.DEFAULT_PAGE_SIZE,
            max_value=self.MAX_PAGE_SIZE,
        )
        offset = (page_number - 1) * page_size

        sql, params = _wa_log_consolidated_sql_and_params(
            tenant_id=tenant.pk,
            start_dt=start_dt,
            end_dt=end_dt,
            flow_execution_id=flow_execution_id,
            limit=page_size,
            offset=offset,
        )
        with connection.cursor() as cursor:
            cursor.execute(sql, params)
            rows = _dictfetchall(cursor)

        total_count = 0
        if rows:
            total_count = rows[0].get("total_count", 0) or 0
            for row in rows:
                row.pop("total_count", None)
        total_pages = (total_count + page_size - 1) // page_size if page_size else 1

        return Response(
            {
                "ok": True,
                "message_count": total_count,
                "messages": rows,
                "pagination": {
                    "current_page": page_number,
                    "total_pages": total_pages or 1,
                    "total_items": total_count,
                },
            }
        )


@method_decorator(csrf_exempt, name="dispatch")
@extend_schema(tags=["communications"])
class CommunicationsSummaryView(ProtectedAPIView, CommunicationsAPIMixin):
    def get(self, request):
        tenant = self._get_tenant_or_none(request)
        if tenant is None:
            return Response({
                "total": 0,
                "active": 0,
                "closed": 0,
                "pending": 0,
                "awaiting_response": 0,
                "total_unread": 0,
                "latest_interaction": None,
                "by_channel": [],
            })

        queryset = AgentSession.objects.filter(tenant=tenant)

        total = queryset.count()
        active = queryset.filter(active=True).count()
        closed = queryset.filter(active=False, end__isnull=False).count()
        pending = queryset.filter(active=False, end__isnull=True).count()

        latest = queryset.aggregate(latest=Max("last_interaction"))
        latest_interaction = self._isoformat(latest.get("latest"))

        latest_role_subquery = (
            SessionThread.objects.filter(session=OuterRef("pk"))
            .order_by("-created")
            .values("role")[:1]
        )
        awaiting_response = queryset.filter(active=True).annotate(
            latest_message_role=Subquery(latest_role_subquery)
        ).filter(latest_message_role__iexact="USER").count()

        try:
            active_sessions = queryset.filter(active=True).annotate(
                last_read_at=Coalesce(
                    Cast(KeyTextTransform("last_read_at", "context"), DateTimeField()),
                    "start"
                )
            )
            unread_subquery = Subquery(
                SessionThread.objects.filter(
                    session=OuterRef("pk"),
                    role__iexact="USER",
                    created__gt=OuterRef("last_read_at")
                ).values("session").annotate(cnt=Count("pk")).values("cnt")[:1]
            )
            sessions_with_unread = active_sessions.annotate(
                unread_count=Coalesce(unread_subquery, Value(0))
            ).aggregate(total_unread=Sum("unread_count"))
            total_unread = sessions_with_unread.get("total_unread") or 0
        except Exception:
            total_unread = SessionThread.objects.filter(
                session__tenant=tenant,
                session__active=True,
                role__iexact="USER"
            ).count()

        channel_stats = (
            queryset.exclude(channel__isnull=True)
            .exclude(channel__exact="")
            .values("channel")
            .annotate(
                total=Count("pk"),
                active_count=Count("pk", filter=Q(active=True)),
            )
        )
        by_channel = [
            {
                "channel": entry["channel"],
                "total": entry["total"],
                "active": entry["active_count"],
            }
            for entry in channel_stats
        ]

        return Response({
            "total": total,
            "active": active,
            "closed": closed,
            "pending": pending,
            "awaiting_response": awaiting_response,
            "total_unread": total_unread,
            "latest_interaction": latest_interaction,
            "by_channel": by_channel,
        })


@method_decorator(csrf_exempt, name="dispatch")
@extend_schema(tags=["dashboard"])
class DashboardSummaryView(ProtectedAPIView):
    def get(self, request):
        return Response(demo_store.dashboard())

@method_decorator(csrf_exempt, name="dispatch")
@extend_schema(tags=["dashboard"])
class ContentNavigationView(ProtectedAPIView):
    def get(self, request):
        return Response(demo_store.navigation_payload())

@method_decorator(csrf_exempt, name="dispatch")
@extend_schema(tags=["dashboard"])
class EngagementTopicsView(ProtectedAPIView):
    def get(self, request):
        return Response(demo_store.topics_payload())


class ContactSummarySerializer(serializers.ModelSerializer):
    id = serializers.SerializerMethodField()
    name = serializers.SerializerMethodField()
    company = serializers.CharField(allow_null=True, read_only=True)
    contacttype = serializers.SerializerMethodField()

    class Meta:
        model = Contact
        fields = ["id", "name", "email", "phone", "title", "company", "contacttype"]

    def get_id(self, obj: Contact) -> str:
        return str(obj.pk)

    def get_name(self, obj: Contact) -> str:
        return (
            obj.display_name
            or obj.fullname
            or obj.whatsapp_name
            or obj.email
            or obj.phone
            or obj.mobile
            or ""
        )

    def get_contacttype(self, obj: Contact) -> Optional[Dict[str, Optional[str]]]:
        ctype = getattr(obj, "ctype", None)
        if ctype is None:
            return None
        return {
            "id": str(ctype.pk),
            "name": ctype.name,
        }


class TicketSerializer(serializers.ModelSerializer):
    creator = ContactSummarySerializer(read_only=True)
    assigned_to = ContactSummarySerializer(source="assigned", read_only=True)
    waiting_for = ContactSummarySerializer(read_only=True)
    type_label = serializers.CharField(source="get_type_display", read_only=True)
    status_label = serializers.CharField(source="get_status_display", read_only=True)
    origin = serializers.SerializerMethodField()
    comments_count = serializers.SerializerMethodField()
    created_at = serializers.SerializerMethodField()
    updated_at = serializers.SerializerMethodField()
    target_at = serializers.SerializerMethodField()
    closed_at = serializers.SerializerMethodField()

    class Meta:
        model = Ticket
        fields = [
            "id",
            "description",
            "service",
            "type",
            "type_label",
            "status",
            "status_label",
            "created_at",
            "updated_at",
            "target_at",
            "closed_at",
            "creator",
            "assigned_to",
            "waiting_for",
            "origin",
            "comments_count",
        ]
        read_only_fields = fields

    def get_origin(self, obj: Ticket) -> Dict[str, Optional[str]]:
        return {
            "type": obj.origin_type,
            "type_label": obj.get_origin_type_display(),
            "ref": obj.origin_ref or None,
            "session_id": str(obj.origin_session_id) if obj.origin_session_id else None,
        }

    def _isoformat(self, dt: Optional[timezone.datetime]) -> Optional[str]:
        if not dt:
            return None
        return (
            dt.astimezone(dt_timezone.utc)
            .replace(microsecond=0)
            .isoformat()
            .replace("+00:00", "Z")
        )

    def get_comments_count(self, obj: Ticket) -> int:
        return obj.comments.count()

    def get_created_at(self, obj: Ticket) -> Optional[str]:
        return self._isoformat(obj.created)

    def get_updated_at(self, obj: Ticket) -> Optional[str]:
        return self._isoformat(obj.last_updated)

    def get_target_at(self, obj: Ticket) -> Optional[str]:
        return self._isoformat(obj.target)

    def get_closed_at(self, obj: Ticket) -> Optional[str]:
        return self._isoformat(obj.closed)


class TicketCreateSerializer(serializers.ModelSerializer):
    contact_id = serializers.UUIDField(write_only=True, required=False, allow_null=True)

    class Meta:
        model = Ticket
        fields = ["id", "description", "service", "type", "contact_id"]
        read_only_fields = ["id"]

    def validate_description(self, value: str) -> str:
        value = (value or "").strip()
        if not value:
            raise serializers.ValidationError("description is required")
        return value

    def validate_type(self, value: str) -> str:
        normalized = (value or "").strip().upper() or "I"
        valid_types = {choice[0] for choice in Ticket.TICKET_TYPE_OPTIONS}
        if normalized not in valid_types:
            raise serializers.ValidationError("type is invalid")
        return normalized

    def validate_service(self, value: str) -> str:
        return (value or "default").strip() or "default"

    def create(self, validated_data: Dict[str, Any]) -> Ticket:
        contact = validated_data.pop("contact", None)
        validated_data.pop("contact_id", None)
        validated_data["creator"] = contact
        return super().create(validated_data)

    def to_representation(self, instance: Ticket) -> Dict[str, Any]:
        return TicketSerializer(instance, context=self.context).data


@method_decorator(csrf_exempt, name="dispatch")
@extend_schema(tags=["tickets"])
class TicketListCreateView(TicketAPIMixin, ProtectedAPIView):
    serializer_class = TicketSerializer
    creation_serializer_class = TicketCreateSerializer

    def get_serializer_class(self):
        if getattr(self.request, "method", "").upper() == "POST":
            return self.creation_serializer_class
        return self.serializer_class

    def get_serializer_context(self):
        return {"request": self.request}

    def get_serializer(self, *args, **kwargs):
        serializer_class = self.get_serializer_class()
        kwargs.setdefault("context", self.get_serializer_context())
        return serializer_class(*args, **kwargs)

    def get(self, request):
        import logging
        logger = logging.getLogger(__name__)
        
        tenant = getattr(request.user, "tenant", None)
        if tenant is None:
            return _error(
                "tenant_not_found",
                "User is not associated with a tenant",
                status.HTTP_403_FORBIDDEN,
            )

        queryset = self._base_queryset(request)
        logger.info(f"[TicketListCreateView] Base queryset count for tenant {tenant.id}: {queryset.count()}")

        status_filter = request.query_params.get("status")
        valid_statuses = {choice[0] for choice in Ticket.TICKET_STATUS_OPTIONS}
        if not status_filter:
            # Default: list only non-closed tickets unless explicitly requested.
            queryset = queryset.exclude(status__iexact="C")
        if status_filter:
            requested = {
                value.strip().upper()
                for value in status_filter.split(",")
                if value.strip()
            }
            filtered = requested & valid_statuses
            if filtered:
                queryset = queryset.filter(status__in=list(filtered))
            else:
                queryset = queryset.none()
            logger.info(f"[TicketListCreateView] After status filter '{status_filter}': {queryset.count()}")

        ticket_type = request.query_params.get("type")
        if ticket_type:
            queryset = queryset.filter(type__iexact=ticket_type.strip())
            logger.info(f"[TicketListCreateView] After type filter '{ticket_type}': {queryset.count()}")

        search = (request.query_params.get("search") or "").strip()
        if search:
            queryset = queryset.filter(
                Q(description__icontains=search) | Q(service__icontains=search)
            )
            logger.info(f"[TicketListCreateView] After search filter '{search}': {queryset.count()}")

        assigned_filter = request.query_params.get("assigned") or request.query_params.get(
            "assigned_to"
        )
        my_tickets = self._parse_bool(request.query_params.get("my_tickets"))
        if my_tickets or (assigned_filter and assigned_filter.lower() == "me"):
            user_contact = self._get_user_contact(request)
            if user_contact:
                queryset = queryset.filter(assigned=user_contact)
            else:
                queryset = queryset.none()
            logger.info(f"[TicketListCreateView] After my_tickets filter: {queryset.count()}")
        elif assigned_filter:
            queryset = queryset.filter(assigned_id=assigned_filter)
            logger.info(f"[TicketListCreateView] After assigned filter '{assigned_filter}': {queryset.count()}")

        total_count = queryset.count()
        logger.info(f"[TicketListCreateView] Final queryset count before pagination: {total_count}")
        
        page_obj, pagination = self._paginate_queryset(queryset, request)
        logger.info(f"[TicketListCreateView] Pagination result: {pagination}")
        
        serializer = self.get_serializer(page_obj.object_list, many=True)
        return Response({"tickets": serializer.data, "pagination": pagination})

    def _resolve_contact(self, request, tenant) -> Optional[Contact]:
        contact_id = request.data.get("creator_id") or request.data.get("contact_id")
        if contact_id:
            try:
                return Contact.objects.get(tenant=tenant, pk=contact_id)
            except (Contact.DoesNotExist, ValueError, TypeError):
                raise ValidationError({"contact_id": "creator contact not found"})
        return self._get_user_contact(request)

    def post(self, request):
        tenant = getattr(request.user, "tenant", None)
        if tenant is None:
            return _error(
                "tenant_not_found",
                "User is not associated with a tenant",
                status.HTTP_403_FORBIDDEN,
            )

        try:
            contact = self._resolve_contact(request, tenant)
        except ValidationError as exc:
            return Response(exc.detail, status=status.HTTP_400_BAD_REQUEST)

        serializer = self.get_serializer(data=request.data)
        if serializer.is_valid():
            serializer.save(tenant=tenant, contact=contact)
            return Response(serializer.data, status=status.HTTP_201_CREATED)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@method_decorator(csrf_exempt, name="dispatch")
@extend_schema(tags=["tickets"])
class TicketDetailView(TicketAPIMixin, ProtectedAPIView):
    def get(self, request, ticket_id):
        ticket = self._find_ticket(request, ticket_id, include_comments=True)
        if ticket is None:
            return _error("ticket_not_found", "Ticket not found", status.HTTP_404_NOT_FOUND)
        return Response(self._serialize_ticket(ticket, include_comments=True))

    def patch(self, request, ticket_id):
        ticket = self._find_ticket(request, ticket_id)
        if ticket is None:
            return _error("ticket_not_found", "Ticket not found", status.HTTP_404_NOT_FOUND)

        data = request.data or {}
        if not data:
            return _error("invalid_request", "No data provided", status.HTTP_400_BAD_REQUEST)

        valid_statuses = {choice[0] for choice in Ticket.TICKET_STATUS_OPTIONS}
        fields_to_update = []

        if "status" in data:
            new_status = (str(data.get("status") or "")).strip().upper()
            if new_status not in valid_statuses:
                return _error("invalid_status", "Invalid status value", status.HTTP_400_BAD_REQUEST)
            ticket.status = new_status
            fields_to_update.append("status")
            ticket.last_updated = timezone.now()
            fields_to_update.append("last_updated")
            if new_status == "C":
                ticket.closed = timezone.now()
            else:
                ticket.closed = None
            fields_to_update.append("closed")
            assignee = self._get_user_contact(request)
            if assignee:
                ticket.assigned = assignee
                fields_to_update.append("assigned")

        if "description" in data:
            ticket.description = str(data.get("description") or "")
            fields_to_update.append("description")

        if "service" in data:
            ticket.service = str(data.get("service") or "")
            fields_to_update.append("service")

        if "priority" in data:
            ticket.priority = data.get("priority")
            fields_to_update.append("priority")

        if "type" in data:
            ticket.type = data.get("type")
            fields_to_update.append("type")

        if not fields_to_update:
            return _error("invalid_request", "No valid fields to update", status.HTTP_400_BAD_REQUEST)

        ticket.save(update_fields=fields_to_update)
        return Response(self._serialize_ticket(ticket))

    def delete(self, request, ticket_id):
        ticket = self._find_ticket(request, ticket_id)
        if ticket is None:
            return _error("ticket_not_found", "Ticket not found", status.HTTP_404_NOT_FOUND)
        ticket.delete()
        return Response({"message": "Ticket deleted"}, status=status.HTTP_200_OK)


@method_decorator(csrf_exempt, name="dispatch")
@extend_schema(tags=["tickets"])
class TicketCommentsView(TicketAPIMixin, ProtectedAPIView):
    def get(self, request, ticket_id):
        ticket = self._find_ticket(request, ticket_id, include_comments=True)
        if ticket is None:
            return _error("ticket_not_found", "Ticket not found", status.HTTP_404_NOT_FOUND)
        comments = getattr(ticket, "prefetched_comments", None)
        if comments is None:
            comments = ticket.comments.select_related("creator").order_by("created")
        return Response({"comments": [self._serialize_comment(c) for c in comments]})

    def post(self, request, ticket_id):
        ticket = self._find_ticket(request, ticket_id)
        if ticket is None:
            return _error("ticket_not_found", "Ticket not found", status.HTTP_404_NOT_FOUND)

        comment_text = request.data.get("comment") or request.data.get("message")
        if not comment_text or not str(comment_text).strip():
            return _error("invalid_request", "comment is required")

        creator = self._get_user_contact(request)
        comment_instance = TicketComment.objects.create(
            ticket=ticket,
            comment=str(comment_text).strip(),
            creator=creator,
        )
        return Response(
            self._serialize_comment(comment_instance), status=status.HTTP_201_CREATED
        )


@method_decorator(csrf_exempt, name="dispatch")
@extend_schema(tags=["tickets"])
class TicketSummaryView(TicketAPIMixin, ProtectedAPIView):
    def get(self, request):
        tenant = getattr(request.user, "tenant", None)
        if tenant is None:
            return _error(
                "tenant_not_found",
                "User is not associated with a tenant",
                status.HTTP_403_FORBIDDEN,
            )

        # Apply the same filters as TicketListCreateView for consistency
        queryset = self._base_queryset(request)

        status_filter = request.query_params.get("status")
        valid_statuses = {choice[0] for choice in Ticket.TICKET_STATUS_OPTIONS}
        if status_filter:
            requested = {
                value.strip().upper()
                for value in status_filter.split(",")
                if value.strip()
            }
            filtered = requested & valid_statuses
            if filtered:
                queryset = queryset.filter(status__in=list(filtered))
            else:
                queryset = queryset.none()

        ticket_type = request.query_params.get("type")
        if ticket_type:
            queryset = queryset.filter(type__iexact=ticket_type.strip())

        search = (request.query_params.get("search") or "").strip()
        if search:
            queryset = queryset.filter(
                Q(description__icontains=search) | Q(service__icontains=search)
            )

        assigned_filter = request.query_params.get("assigned") or request.query_params.get(
            "assigned_to"
        )
        my_tickets = self._parse_bool(request.query_params.get("my_tickets"))
        if my_tickets or (assigned_filter and assigned_filter.lower() == "me"):
            user_contact = self._get_user_contact(request)
            if user_contact:
                queryset = queryset.filter(assigned=user_contact)
            else:
                queryset = queryset.none()
        elif assigned_filter:
            queryset = queryset.filter(assigned_id=assigned_filter)

        return Response(TicketService.get_ticket_counts(tenant, queryset=queryset))

