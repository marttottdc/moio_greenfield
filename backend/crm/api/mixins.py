from __future__ import annotations

import uuid
from datetime import datetime, timezone as dt_timezone
from typing import Any, Dict, List, Optional, Callable

from django.conf import settings
from django.core.paginator import Paginator
from django.db.models import Prefetch, QuerySet
from django.utils import timezone
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework_simplejwt.authentication import JWTAuthentication

from crm.models import Contact, ContactType, Ticket, TicketComment
from chatbot.models.chatbot_session import ChatbotMemory, ChatbotSession
from moio_platform.authentication import BearerTokenAuthentication
from central_hub.authentication import CsrfExemptSessionAuthentication, TenantJWTAAuthentication, UserApiKeyAuthentication


def _error(code: str, message: str, http_status: int) -> Response:
    return Response({"error": code, "message": message}, status=http_status)


class ProtectedAPIView(APIView):
    """
    Base API view for authenticated endpoints.
    Uses CsrfExemptSessionAuthentication to allow POST/PUT/PATCH/DELETE
    without CSRF tokens - appropriate for token-authenticated REST APIs.
    """
    authentication_classes = [
        CsrfExemptSessionAuthentication,
        UserApiKeyAuthentication,
        TenantJWTAAuthentication,
        BearerTokenAuthentication,
        JWTAuthentication,
    ]
    permission_classes = [IsAuthenticated]


class TenantScopedMixin:
    def get_object(self):
        obj = super().get_object()
        tenant = getattr(self.request.user, "tenant_id", None)
        if tenant is None or getattr(obj, "tenant_id", None) != tenant:
            raise PermissionDenied("Forbidden: cross-tenant access blocked.")
        return obj


class PaginationMixin:
    DEFAULT_PAGE_SIZE = 50
    MAX_PAGE_SIZE = 100
    MIN_PAGE_SIZE = 1
    ITEMS_KEY = "items"

    def _isoformat(self, dt) -> Optional[str]:
        if not dt:
            return None
        if isinstance(dt, str):
            try:
                normalized = dt.replace("Z", "+00:00")
                parsed = datetime.fromisoformat(normalized)
                if timezone.is_naive(parsed):
                    parsed = timezone.make_aware(parsed, timezone=dt_timezone.utc)
                dt = parsed
            except (ValueError, TypeError):
                return dt
        return (
            dt.astimezone(dt_timezone.utc)
            .replace(microsecond=0)
            .isoformat()
            .replace("+00:00", "Z")
        )

    def _parse_page_params(self, request) -> tuple[int, int]:
        try:
            page = int(request.query_params.get("page", 1))
        except ValueError:
            raise ValidationError({"page": "Must be an integer"})
        try:
            limit = int(request.query_params.get("limit", self.DEFAULT_PAGE_SIZE))
        except ValueError:
            raise ValidationError({"limit": "Must be an integer"})
        limit = max(self.MIN_PAGE_SIZE, min(limit, self.MAX_PAGE_SIZE))
        page = max(page, 1)
        return page, limit

    def _get_tenant(self, request):
        tenant = self._resolve_tenant_for_request(request)
        if tenant is None:
            raise ValidationError({"tenant": "User must belong to a tenant"})
        return tenant

    def _resolve_tenant_for_request(self, request):
        """Resolve tenant from user, context, or JWT (fixes 'relation does not exist' when middleware runs before auth)."""
        tenant = getattr(request.user, "tenant", None)
        if tenant and getattr(tenant, "schema_name", None):
            return tenant
        try:
            from tenancy.context_utils import current_tenant

            tenant = current_tenant.get()
        except Exception:
            tenant = None
        if tenant and getattr(tenant, "schema_name", None):
            return tenant
        try:
            from tenancy.host_rewrite import _get_tenant_schema_from_jwt
            from tenancy.models import Tenant
            from tenancy.tenant_support import public_schema_name

            schema_name = _get_tenant_schema_from_jwt(request)
            if not schema_name:
                return None
            try:
                from django_tenants.utils import schema_context

                with schema_context(public_schema_name()):
                    return Tenant.objects.filter(schema_name=schema_name).first()
            except Exception:
                return Tenant.objects.filter(schema_name=schema_name).first()
        except Exception:
            return None

    def _get_tenant_or_none(self, request):
        return self._resolve_tenant_for_request(request)

    def _ensure_tenant_schema(self, request):
        """Ensure DB connection uses tenant schema before tenant-scoped queries (fixes 'relation does not exist')."""
        tenant = self._resolve_tenant_for_request(request)
        if not tenant or not getattr(tenant, "schema_name", None):
            return
        if not getattr(settings, "DJANGO_TENANTS_ENABLED", False):
            return
        try:
            from django.db import connection

            connection.set_tenant(tenant)
        except Exception:
            pass

    def _paginate(
        self,
        queryset: QuerySet,
        request,
        serializer: Optional[Callable] = None,
        items_key: Optional[str] = None,
    ) -> Dict[str, Any]:
        self._ensure_tenant_schema(request)
        page, limit = self._parse_page_params(request)
        start = (page - 1) * limit
        end = start + limit
        total = queryset.count()

        items = list(queryset[start:end])
        if serializer:
            items = [serializer(item) for item in items]

        key = items_key or self.ITEMS_KEY
        pagination = {
            "current_page": page,
            "total_pages": (total + limit - 1) // limit if limit else 1,
            "total_items": total,
            "items_per_page": limit,
        }
        return {key: items, "pagination": pagination}


class CommunicationsAPIMixin:
    DEFAULT_PAGE_SIZE = 25
    MAX_PAGE_SIZE = 100

    def _isoformat(self, dt) -> Optional[str]:
        if not dt:
            return None
        if isinstance(dt, str):
            try:
                parsed = datetime.fromisoformat(dt.replace("Z", "+00:00"))
                if timezone.is_naive(parsed):
                    parsed = timezone.make_aware(parsed, timezone=dt_timezone.utc)
                dt = parsed
            except (ValueError, TypeError):
                return dt
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
        tenant = getattr(request.user, "tenant", None)
        if tenant is None:
            return ChatbotSession.objects.none()
        base_qs = ChatbotSession.objects.filter(tenant=tenant).select_related("contact")
        messages_prefetch = Prefetch(
            "memory_thread",
            queryset=ChatbotMemory.objects.order_by("-created")[:50],
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
            except Exception:
                avatar_url = contact.image.url
        return {
            "id": str(contact.user_id),
            "name": display_name,
            "phone": contact.phone or contact.mobile or "",
            "email": contact.email or "",
            "avatar_url": avatar_url,
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

    def _serialize_message(self, message: ChatbotMemory, contact: Contact) -> Dict[str, Any]:
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
        return ["text", "image", "video", "audio", "document", "location"]

    def _conversation_status(self, session: ChatbotSession) -> str:
        if session.active:
            return "active"
        if session.end:
            return "closed"
        return "pending"

    def _get_last_message(self, session: ChatbotSession) -> Optional[ChatbotMemory]:
        messages = getattr(session, "prefetched_messages", None)
        if messages:
            return messages[0]
        return session.memory_thread.order_by("-created").first()

    def _get_session_for_request(self, request, session_id: str) -> Optional[ChatbotSession]:
        queryset = self._tenant_sessions_queryset(request)
        try:
            return queryset.get(pk=session_id)
        except ChatbotSession.DoesNotExist:
            return None

    def _unread_count(self, session: ChatbotSession) -> int:
        context = session.context or {}
        last_read_at_raw = context.get("last_read_at") if isinstance(context, dict) else None
        last_read_at = self._parse_iso_datetime(last_read_at_raw)
        qs = session.memory_thread.filter(role__iexact="USER")
        if last_read_at:
            qs = qs.filter(created__gt=last_read_at)
        return qs.count()

    def _serialize_session_with_metadata(self, request, session: ChatbotSession) -> Dict[str, Any]:
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
                "total_messages": session.memory_thread.count(),
                "ai_summary": session.final_summary or "",
            },
            "unread_count": self._unread_count(session),
            "tags": self._conversation_tags(session.contact),
        }


_UNSET = object()


class ContactAPIMixin:
    SORTABLE_FIELDS = {
        "created_at": "created",
        "updated_at": "updated",
        "name": "fullname",
        "email": "email",
        "phone": "phone",
    }

    def _isoformat(self, dt) -> Optional[str]:
        if not dt:
            return None
        if isinstance(dt, str):
            try:
                parsed = datetime.fromisoformat(dt.replace("Z", "+00:00"))
                if timezone.is_naive(parsed):
                    parsed = timezone.make_aware(parsed, timezone=dt_timezone.utc)
                dt = parsed
            except (ValueError, TypeError):
                return dt
        return (
            dt.astimezone(dt_timezone.utc)
            .replace(microsecond=0)
            .isoformat()
            .replace("+00:00", "Z")
        )

    def _base_queryset(self, request):
        tenant = getattr(request.user, "tenant", None)
        if tenant is None:
            return Contact.objects.none()
        return (
            Contact.objects.filter(tenant=tenant)
            .select_related("ctype")
            .prefetch_related("customer_contacts__customer")
        )

    def _default_activity_summary(self) -> Dict[str, Optional[Any]]:
        return {
            "total_deals": 0,
            "total_tickets": 0,
            "total_messages": 0,
            "last_contact": None,
        }

    def _normalize_tags(self, value) -> List[str]:
        if value is None:
            return []
        if isinstance(value, str):
            tokens = [token.strip() for token in value.split(",")]
            return [token for token in tokens if token]
        if isinstance(value, list):
            normalized = []
            for item in value:
                if item is None:
                    continue
                token = str(item).strip()
                if token:
                    normalized.append(token)
            return normalized
        raise ValueError("tags must be provided as a list or comma separated string")

    def _normalize_custom_fields(self, value) -> Dict[str, Any]:
        if value is None:
            return {}
        if isinstance(value, dict):
            return value
        raise ValueError("custom_fields must be an object")

    def _normalize_activity_summary(self, value) -> Dict[str, Any]:
        if value is None:
            return {}
        if not isinstance(value, dict):
            raise ValueError("activity_summary must be an object")
        summary = self._default_activity_summary()
        summary.update({k: value.get(k, summary[k]) for k in summary.keys()})
        return summary

    def _apply_meta_updates(
        self,
        contact: Contact,
        *,
        tags=_UNSET,
        custom_fields=_UNSET,
        activity_summary=_UNSET,
    ) -> bool:
        facts = dict(contact.brief_facts or {})
        changed = False
        if tags is not _UNSET:
            facts["tags"] = tags
            changed = True
        if custom_fields is not _UNSET:
            facts["custom_fields"] = custom_fields
            changed = True
        if activity_summary is not _UNSET:
            facts["activity_summary"] = activity_summary
            changed = True
        if changed:
            contact.brief_facts = facts
        return changed

    def _resolve_contact_type(self, tenant, raw_value) -> tuple[Optional[ContactType], Optional[str]]:
        if raw_value in (None, ""):
            return None, None
        identifier: Optional[str]
        if isinstance(raw_value, dict):
            identifier = raw_value.get("id") or raw_value.get("name")
        else:
            identifier = str(raw_value).strip()
        if not identifier:
            return None, "contact type identifier is empty"
        queryset = ContactType.objects.filter(tenant=tenant)
        contact_type: Optional[ContactType] = None
        try:
            contact_uuid = uuid.UUID(str(identifier))
        except (ValueError, TypeError):
            contact_type = queryset.filter(name__iexact=identifier).first()
        else:
            contact_type = queryset.filter(id=contact_uuid).first()
        if contact_type is None:
            return None, "contact type not found"
        return contact_type, None

    def _serialize_contact(self, contact: Contact) -> Dict[str, Any]:
        facts = contact.brief_facts or {}
        tags = facts.get("tags") if isinstance(facts.get("tags"), list) else []
        custom_fields = facts.get("custom_fields") if isinstance(facts.get("custom_fields"), dict) else {}
        activity = facts.get("activity_summary") if isinstance(facts.get("activity_summary"), dict) else {}
        summary = {**self._default_activity_summary(), **activity}
        if not summary.get("total_messages"):
            summary["total_messages"] = contact.interactions_count or 0
        if not summary.get("last_contact"):
            summary["last_contact"] = self._isoformat(
                contact.last_contacted_at or contact.last_seen_at or contact.updated
            )

        account_name = None
        if hasattr(contact, "customer_contacts"):
            for cc in contact.customer_contacts.all():
                if getattr(cc, "customer", None) and getattr(cc.customer, "name", None):
                    account_name = cc.customer.name
                    break

        return {
            "id": str(contact.pk),
            "name": contact.fullname or contact.display_name or contact.whatsapp_name or contact.email,
            "email": contact.email or None,
            "phone": contact.phone or None,
            "company": contact.company or None,
            "account_name": account_name,
            "type": contact.ctype.name if contact.ctype else None,
            "is_blacklisted": bool(getattr(contact, "is_blacklisted", False)),
            "do_not_contact": bool(getattr(contact, "do_not_contact", False)),
            "tags": tags,
            "custom_fields": custom_fields,
            "activity_summary": summary,
            "created_at": self._isoformat(contact.created),
            "updated_at": self._isoformat(contact.updated),
        }


class TicketAPIMixin:
    DEFAULT_PAGE_SIZE = 25
    MAX_PAGE_SIZE = 100

    def _isoformat(self, dt) -> Optional[str]:
        if not dt:
            return None
        if isinstance(dt, str):
            try:
                parsed = datetime.fromisoformat(dt.replace("Z", "+00:00"))
                if timezone.is_naive(parsed):
                    parsed = timezone.make_aware(parsed, timezone=dt_timezone.utc)
                dt = parsed
            except (ValueError, TypeError):
                return dt
        return (
            dt.astimezone(dt_timezone.utc)
            .replace(microsecond=0)
            .isoformat()
            .replace("+00:00", "Z")
        )

    def _parse_bool(self, value: Optional[str]) -> bool:
        if value is None:
            return False
        if isinstance(value, bool):
            return value
        normalized = str(value).strip().lower()
        return normalized in {"1", "true", "yes", "on"}

    def _parse_int(
        self,
        value: Optional[str],
        *,
        default: int,
        min_value: int = 1,
        max_value: Optional[int] = None,
    ) -> int:
        try:
            parsed = int(value)
        except (TypeError, ValueError):
            parsed = default
        parsed = max(min_value, parsed)
        if max_value is not None:
            parsed = min(max_value, parsed)
        return parsed

    def _comments_prefetch(self):
        return Prefetch(
            "comments",
            queryset=TicketComment.objects.select_related("creator").order_by("created"),
            to_attr="prefetched_comments",
        )

    def _base_queryset(self, request):
        tenant = getattr(request.user, "tenant", None)
        if tenant is None:
            return Ticket.objects.none()
        return (
            Ticket.objects.filter(tenant=tenant)
            .select_related(
                "creator", "creator__ctype",
                "assigned", "assigned__ctype",
                "waiting_for", "waiting_for__ctype",
                "origin_session"
            )
            .order_by("-created")
        )

    def _serialize_contact(self, contact: Optional[Contact]) -> Optional[Dict[str, Optional[str]]]:
        if contact is None:
            return None
        display_name = (
            contact.display_name
            or contact.fullname
            or contact.whatsapp_name
            or contact.email
            or contact.phone
            or contact.mobile
            or ""
        )
        ctype = getattr(contact, "ctype", None)
        return {
            "id": str(contact.pk),
            "name": display_name,
            "email": contact.email or None,
            "phone": contact.phone or contact.mobile or None,
            "title": contact.title or "",
            "company": contact.company or None,
            "contacttype": {
                "id": str(ctype.pk) if ctype else None,
                "name": ctype.name if ctype else None,
            } if ctype else None,
        }

    def _serialize_comment(self, comment: TicketComment) -> Dict[str, Optional[str]]:
        return {
            "id": str(comment.pk),
            "comment": comment.comment,
            "created_at": self._isoformat(comment.created),
            "creator": self._serialize_contact(comment.creator),
        }

    def _serialize_ticket(
        self,
        ticket: Ticket,
        *,
        include_comments: bool = False,
    ) -> Dict[str, Any]:
        payload = {
            "id": str(ticket.pk),
            "description": ticket.description,
            "service": ticket.service,
            "type": ticket.type,
            "type_label": ticket.get_type_display(),
            "status": ticket.status,
            "status_label": ticket.get_status_display(),
            "created_at": self._isoformat(ticket.created),
            "updated_at": self._isoformat(ticket.last_updated),
            "target_at": self._isoformat(ticket.target),
            "closed_at": self._isoformat(ticket.closed),
            "creator": self._serialize_contact(ticket.creator),
            "assigned_to": self._serialize_contact(ticket.assigned),
            "waiting_for": self._serialize_contact(ticket.waiting_for),
            "origin": {
                "type": ticket.origin_type,
                "type_label": ticket.get_origin_type_display(),
                "ref": ticket.origin_ref or None,
                "session_id": ticket.origin_session_id or None,
            },
        }
        if include_comments:
            comments = getattr(ticket, "prefetched_comments", None)
            if comments is None:
                comments = ticket.comments.select_related("creator").order_by("created")
            payload["comments"] = [self._serialize_comment(comment) for comment in comments]
        else:
            payload["comments_count"] = ticket.comments.count()
        return payload

    def _paginate_queryset(self, queryset, request):
        page = self._parse_int(request.query_params.get("page"), default=1, min_value=1)
        page_size = self._parse_int(
            request.query_params.get("page_size"),
            default=self.DEFAULT_PAGE_SIZE,
            min_value=1,
            max_value=self.MAX_PAGE_SIZE,
        )
        paginator = Paginator(queryset, page_size)
        page_obj = paginator.get_page(page)
        total_pages = paginator.num_pages or 0
        pagination = {
            "current_page": page_obj.number,
            "total_pages": total_pages,
            "total_items": paginator.count,
            "items_per_page": page_obj.paginator.per_page,
        }
        return page_obj, pagination

    def _get_user_contact(self, request) -> Optional[Contact]:
        tenant = getattr(request.user, "tenant", None)
        email = getattr(request.user, "email", None)
        if not tenant or not email:
            return None
        return Contact.objects.filter(tenant=tenant, email__iexact=email).first()

    def _find_ticket(self, request, ticket_id, *, include_comments: bool = False) -> Optional[Ticket]:
        queryset = self._base_queryset(request)
        if include_comments:
            queryset = queryset.prefetch_related(self._comments_prefetch())
        try:
            return queryset.get(pk=ticket_id)
        except Ticket.DoesNotExist:
            return None
