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

from crm.models import Contact, ContactType, Ticket, TicketComment, Customer, CustomerContact
from crm.services.contact import normalize_phone_e164, sync_whatsapp_blocklist
from chatbot.models.chatbot_session import ChatbotMemory, ChatbotSession
from chatbot.core.human_mode_context import append_context_message

from .data_store import demo_store
from crm.services.ticket_service import TicketService


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


class CommunicationsAPIMixin:
    DEFAULT_PAGE_SIZE = 25
    MAX_PAGE_SIZE = 100

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
        tenant = getattr(request.user, "tenant", None)
        if tenant is None:
            return ChatbotSession.objects.none()
        base_qs = ChatbotSession.objects.filter(tenant=tenant).select_related("contact", "contact__ctype")
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
        # default to WhatsApp-style rich messaging
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

    def _serialize_conversation_summary(self, request, session: ChatbotSession) -> Dict[str, Any]:
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


class ContactAPIMixin:
    SORTABLE_FIELDS = {
        "created_at": "created",
        "updated_at": "updated",
        "name": "fullname",
        "email": "email",
        "phone": "phone",
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

    def _base_queryset(self, request):
        tenant = getattr(request.user, "tenant", None)
        if tenant is None:
            return Contact.objects.none()
        return Contact.objects.filter(tenant=tenant).select_related("ctype")

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

        account_ids = [
            str(cc.customer_id) for cc in contact.customer_contacts.all()
        ] if hasattr(contact, "customer_contacts") else []
        return {
            "id": str(contact.pk),
            "name": contact.fullname or contact.display_name or contact.whatsapp_name or contact.email,
            "email": contact.email or None,
            "phone": contact.phone or None,
            "company": contact.company or None,
            "type": contact.ctype.name if contact.ctype else None,
            "is_blacklisted": bool(getattr(contact, "is_blacklisted", False)),
            "tags": tags,
            "custom_fields": custom_fields,
            "activity_summary": summary,
            "account_ids": account_ids,
            "created_at": self._isoformat(contact.created),
            "updated_at": self._isoformat(contact.updated),
        }


@method_decorator(csrf_exempt, name="dispatch")
@extend_schema(tags=["contacts"])
class ContactDetailView(ContactAPIMixin, ProtectedAPIView):
    def _get_contact(self, request, contact_id) -> Optional[Contact]:
        tenant = getattr(request.user, "tenant", None)
        if tenant is None:
            return None
        return (
            Contact.objects.select_related("ctype")
            .filter(tenant=tenant, pk=contact_id)
            .first()
        )

    def get(self, request, contact_id):
        contact = self._get_contact(request, contact_id)
        if not contact:
            return _error("contact_not_found", "Contact not found", status.HTTP_404_NOT_FOUND)
        return Response(self._serialize_contact(contact))

    def patch(self, request, contact_id):
        contact = self._get_contact(request, contact_id)
        if not contact:
            return _error("contact_not_found", "Contact not found", status.HTTP_404_NOT_FOUND)
        payload = request.data or {}
        fields_to_update: List[str] = []
        if "name" in payload or "fullname" in payload:
            name = payload.get("name") or payload.get("fullname") or ""
            contact.fullname = str(name).strip()
            fields_to_update.append("fullname")
        if "email" in payload:
            contact.email = payload.get("email", "")
            fields_to_update.append("email")
        if "phone" in payload:
            phone_value, phone_error = _normalize_and_validate_phone(payload.get("phone", ""))
            if phone_error is not None:
                return phone_error
            contact.phone = phone_value
            fields_to_update.append("phone")
        if "company" in payload:
            contact.company = payload.get("company", "")
            fields_to_update.append("company")
        if "is_blacklisted" in payload:
            contact.is_blacklisted = bool(payload.get("is_blacklisted"))
            fields_to_update.append("is_blacklisted")
        if "type" in payload:
            contact_type, error = self._resolve_contact_type(getattr(request.user, "tenant", None), payload.get("type"))
            if error:
                return _error("invalid_contact_type", error, status.HTTP_400_BAD_REQUEST)
            contact.ctype = contact_type
            fields_to_update.append("ctype")

        try:
            tags = self._normalize_tags(payload.get("tags")) if "tags" in payload else _UNSET
            custom_fields = (
                self._normalize_custom_fields(payload.get("custom_fields"))
                if "custom_fields" in payload
                else _UNSET
            )
            activity_summary = (
                self._normalize_activity_summary(payload.get("activity_summary"))
                if "activity_summary" in payload
                else _UNSET
            )
        except ValueError as exc:
            return _error("invalid_request", str(exc), status.HTTP_400_BAD_REQUEST)

        if (
            tags is not _UNSET
            or custom_fields is not _UNSET
            or activity_summary is not _UNSET
        ):
            changed = self._apply_meta_updates(
                contact,
                tags=tags,
                custom_fields=custom_fields,
                activity_summary=activity_summary,
            )
            if changed:
                fields_to_update.append("brief_facts")

        if fields_to_update:
            fields_to_update.append("updated")
            contact.save(update_fields=fields_to_update)
            if "is_blacklisted" in fields_to_update:
                sync_whatsapp_blocklist(contact, enabled=contact.is_blacklisted)
        if "account_ids" in payload:
            tenant = getattr(request.user, "tenant", None)
            if tenant is not None:
                desired = set()
                for cid in payload.get("account_ids") or []:
                    try:
                        cust_id = uuid.UUID(str(cid))
                    except (ValueError, TypeError):
                        continue
                    if Customer.objects.filter(tenant=tenant, id=cust_id).exists():
                        desired.add(cust_id)
                existing_ids = set(
                    CustomerContact.objects.filter(contact=contact).values_list("customer_id", flat=True)
                )
                for cust_id in desired:
                    if cust_id not in existing_ids:
                        CustomerContact.objects.get_or_create(
                            tenant=tenant,
                            customer_id=cust_id,
                            contact=contact,
                            defaults={"role": ""},
                        )
                for cust_id in existing_ids:
                    if cust_id not in desired:
                        CustomerContact.objects.filter(
                            contact=contact, customer_id=cust_id
                        ).delete()
        return Response(self._serialize_contact(contact))

    def delete(self, request, contact_id):
        contact = self._get_contact(request, contact_id)
        if not contact:
            return _error("contact_not_found", "Contact not found", status.HTTP_404_NOT_FOUND)
        contact.delete()
        return Response({"message": "Contact deleted successfully"})


@method_decorator(csrf_exempt, name="dispatch")
@extend_schema(tags=["contacts"])
class ContactsSummaryView(ContactAPIMixin, ProtectedAPIView):
    def get(self, request):
        tenant = getattr(request.user, "tenant", None)
        if tenant is None:
            return Response({
                "total": 0,
                "with_email": 0,
                "with_phone": 0,
                "do_not_contact": 0,
                "bounced": 0,
                "latest_updated": None,
                "by_type": [],
            })

        queryset = Contact.objects.filter(tenant=tenant, is_deleted=False)

        total = queryset.count()
        with_email = queryset.exclude(email__isnull=True).exclude(email__exact="").count()
        with_phone = queryset.filter(
            Q(phone__isnull=False) & ~Q(phone__exact="") |
            Q(mobile__isnull=False) & ~Q(mobile__exact="")
        ).count()
        do_not_contact = queryset.filter(do_not_contact=True).count()
        bounced = queryset.filter(bounced=True).count()

        latest = queryset.aggregate(latest=Max("updated"))
        latest_updated = self._isoformat(latest.get("latest"))

        type_stats = (
            queryset.exclude(ctype__isnull=True)
            .values("ctype__name")
            .annotate(count=Count("pk"))
            .order_by("-count")
        )
        by_type = [
            {"type": entry["ctype__name"], "count": entry["count"]}
            for entry in type_stats
        ]

        return Response({
            "total": total,
            "with_email": with_email,
            "with_phone": with_phone,
            "do_not_contact": do_not_contact,
            "bounced": bounced,
            "latest_updated": latest_updated,
            "by_type": by_type,
        })


@method_decorator(csrf_exempt, name="dispatch")
@extend_schema(tags=["contacts"])
class ContactsView(ContactAPIMixin, ProtectedAPIView):
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
        total = queryset.count()
        contacts = [self._serialize_contact(contact) for contact in queryset[start:end]]
        pagination = {
            "current_page": page,
            "total_pages": (total + limit - 1) // limit if limit else 1,
            "total_items": total,
            "items_per_page": limit,
        }
        return {"contacts": contacts, "pagination": pagination}

    def get(self, request):
        queryset = self._base_queryset(request)
        account_id = request.query_params.get("account_id")
        if account_id:
            try:
                uuid.UUID(str(account_id))
                tenant = getattr(request.user, "tenant", None)
                if tenant:
                    customer = Customer.objects.filter(tenant=tenant, id=account_id).first()
                    if customer:
                        conditions = Q(customer_contacts__customer_id=account_id)
                        if customer.name and len(str(customer.name).strip()) > 0:
                            conditions |= Q(company__iexact=customer.name.strip())
                        queryset = queryset.filter(conditions).distinct()
                    else:
                        queryset = queryset.filter(customer_contacts__customer_id=account_id).distinct()
                else:
                    queryset = queryset.filter(customer_contacts__customer_id=account_id).distinct()
            except (ValueError, TypeError):
                return _error("invalid_account_id", "account_id must be a valid UUID", status.HTTP_400_BAD_REQUEST)
        search = (request.query_params.get("search") or "").strip()
        if search:
            queryset = queryset.filter(
                Q(fullname__icontains=search)
                | Q(email__icontains=search)
                | Q(phone__icontains=search)
                | Q(whatsapp_name__icontains=search)
            )
        type_filter = request.query_params.get("type")
        if type_filter:
            contact_type, error = self._resolve_contact_type(getattr(request.user, "tenant", None), type_filter)
            if error:
                return _error("invalid_contact_type", error, status.HTTP_400_BAD_REQUEST)
            queryset = queryset.filter(ctype=contact_type)

        sort_by = request.query_params.get("sort_by", "created_at")
        sort_field = self.SORTABLE_FIELDS.get(sort_by, "created")
        order = request.query_params.get("order", "desc")
        prefix = "-" if order == "desc" else ""
        queryset = queryset.order_by(f"{prefix}{sort_field}")
        return Response(self._paginate(queryset, request))

    def post(self, request):
        payload = request.data or {}
        raw_name = payload.get("name") or payload.get("fullname") or payload.get("whatsapp_name")
        if not raw_name:
            return _error("invalid_request", "name is required", status.HTTP_400_BAD_REQUEST)
        name = str(raw_name).strip()
        if not name:
            return _error("invalid_request", "name is required", status.HTTP_400_BAD_REQUEST)
        tenant = getattr(request.user, "tenant", None)
        if tenant is None:
            return _error("tenant_required", "User must belong to a tenant", status.HTTP_400_BAD_REQUEST)
        contact_type, error = self._resolve_contact_type(tenant, payload.get("type"))
        if error:
            return _error("invalid_contact_type", error, status.HTTP_400_BAD_REQUEST)

        try:
            tags = self._normalize_tags(payload.get("tags")) if "tags" in payload else []
            custom_fields = (
                self._normalize_custom_fields(payload.get("custom_fields"))
                if "custom_fields" in payload
                else {}
            )
            activity_summary = (
                self._normalize_activity_summary(payload.get("activity_summary"))
                if "activity_summary" in payload
                else {}
            )
        except ValueError as exc:
            return _error("invalid_request", str(exc), status.HTTP_400_BAD_REQUEST)

        phone_value, phone_error = _normalize_and_validate_phone(payload.get("phone", ""))
        if phone_error is not None:
            return phone_error

        try:
            contact = Contact.objects.create(
                tenant=tenant,
                fullname=name,
                email=payload.get("email", ""),
                phone=phone_value,
                company=payload.get("company", ""),
                ctype=contact_type,
                source=payload.get("source", "api"),
                created_by=request.user,
                is_blacklisted=bool(payload.get("is_blacklisted")),
            )
        except (IntegrityError, DataError):
            return Response(
                {
                    "error": "invalid_request",
                    "message": "Invalid contact data (e.g. phone/email length or duplicate).",
                    "details": {"phone": ["Check length and uniqueness per tenant."]},
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        if self._apply_meta_updates(
            contact,
            tags=tags,
            custom_fields=custom_fields,
            activity_summary=activity_summary,
        ):
            contact.save(update_fields=["brief_facts"])
        if contact.is_blacklisted:
            sync_whatsapp_blocklist(contact, enabled=True)
        account_ids = payload.get("account_ids")
        if isinstance(account_ids, (list, tuple)) and len(account_ids) > 0:
            for cid in account_ids:
                try:
                    cust_id = uuid.UUID(str(cid))
                except (ValueError, TypeError):
                    continue
                if Customer.objects.filter(tenant=tenant, id=cust_id).exists():
                    CustomerContact.objects.get_or_create(
                        tenant=tenant,
                        customer_id=cust_id,
                        contact=contact,
                        defaults={"role": ""},
                    )
        return Response(self._serialize_contact(contact), status=status.HTTP_201_CREATED)


@method_decorator(csrf_exempt, name="dispatch")
@extend_schema(tags=["contacts"])
class ContactExportView(ContactAPIMixin, ProtectedAPIView):
    def get(self, request):
        export_format = (request.query_params.get("format") or "csv").lower()
        if export_format not in {"csv", "json"}:
            return _error("invalid_format", "format must be csv or json", status.HTTP_400_BAD_REQUEST)
        queryset = self._base_queryset(request)
        filters: Dict[str, Any] = {}

        type_filter = request.query_params.get("type")
        if type_filter:
            contact_type, error = self._resolve_contact_type(getattr(request.user, "tenant", None), type_filter)
            if error:
                return _error("invalid_contact_type", error, status.HTTP_400_BAD_REQUEST)
            queryset = queryset.filter(ctype=contact_type)
            filters["type"] = contact_type.name

        contacts = list(queryset)
        tags_filter = request.query_params.get("tags")
        if tags_filter:
            try:
                desired_tags = [tag.lower() for tag in self._normalize_tags(tags_filter)]
            except ValueError as exc:
                return _error("invalid_request", str(exc), status.HTTP_400_BAD_REQUEST)
            if desired_tags:
                filters["tags"] = desired_tags

                def _matches(contact: Contact) -> bool:
                    facts = contact.brief_facts or {}
                    contact_tags = facts.get("tags") if isinstance(facts.get("tags"), list) else []
                    present = {tag.lower() for tag in contact_tags}
                    return all(tag in present for tag in desired_tags)

                contacts = [contact for contact in contacts if _matches(contact)]

        total_contacts = len(contacts)
        export_id = str(uuid.uuid4())
        payload = {
            "export_id": export_id,
            "format": export_format,
            "filters": filters,
            "total_contacts": total_contacts,
            "generated_at": self._isoformat(timezone.now()),
            "download_url": f"https://cdn.moio.ai/exports/{export_id}.{export_format}",
            "preview": [self._serialize_contact(contact) for contact in contacts[:10]],
        }
        return Response(payload)


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
            ChatbotMemory.objects.filter(session=OuterRef("pk"))
            .order_by("-created")
            .values("created")[:1]
        )
        latest_role_subquery = (
            ChatbotMemory.objects.filter(session=OuterRef("pk"))
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
        tenant = getattr(request.user, "tenant", None)
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
        session = ChatbotSession.objects.create(
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

        messages_qs = session.memory_thread.order_by("-created")
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
            try:
                from chatbot.core.messenger import Messenger
                from central_hub.models import TenantConfiguration

                config = TenantConfiguration.objects.get(tenant=session.tenant)
                messenger = Messenger(channel=session.channel, config=config, client_name="human_mode")
                delivery_report = messenger.just_reply_with_report(content, session.contact.phone)
                send_success = bool(delivery_report.get("success", False))
                sent_items = delivery_report.get("sent_items") or []

                if not send_success or not sent_items:
                    return _error("send_failed", "Failed to send message to contact", status.HTTP_500_INTERNAL_SERVER_ERROR)

                delivered_content = sent_items[0]
                message = ChatbotMemory.objects.create(
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
            message = ChatbotMemory.objects.create(
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
            session.memory_thread.filter(role__iexact="USER").order_by("-created").first()
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
        tenant = getattr(request.user, "tenant", None)
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
        tenant = getattr(request.user, "tenant", None)
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

        queryset = ChatbotSession.objects.filter(tenant=tenant)

        total = queryset.count()
        active = queryset.filter(active=True).count()
        closed = queryset.filter(active=False, end__isnull=False).count()
        pending = queryset.filter(active=False, end__isnull=True).count()

        latest = queryset.aggregate(latest=Max("last_interaction"))
        latest_interaction = self._isoformat(latest.get("latest"))

        latest_role_subquery = (
            ChatbotMemory.objects.filter(session=OuterRef("pk"))
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
                ChatbotMemory.objects.filter(
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
            total_unread = ChatbotMemory.objects.filter(
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


class TicketAPIMixin:
    DEFAULT_PAGE_SIZE = 25
    MAX_PAGE_SIZE = 100

    def _isoformat(self, dt: Optional[timezone.datetime]) -> Optional[str]:
        if not dt:
            return None
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
            "items_per_page": page_size,
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

