from __future__ import annotations

import uuid
from typing import Any, Dict, Optional

from django.db.models import Q
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt
from drf_spectacular.utils import extend_schema, OpenApiParameter, OpenApiExample, OpenApiResponse
from drf_spectacular.types import OpenApiTypes
from rest_framework import status, serializers
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response

from crm.models import Contact, Customer

from crm.api.contacts.serializers import ContactCreateSerializer
from crm.api.mixins import ContactAPIMixin, ProtectedAPIView, _UNSET, _error
from tenancy.rbac import user_has_role
from tenancy.tenant_support import tenant_rls_context
from crm.services.contact_service import ContactService
from crm.services.contact import sync_whatsapp_blocklist, normalize_phone_e164
from moio_platform.core.events import emit_event
from moio_platform.core.events.snapshots import snapshot_contact
from moio_platform.api_schemas import Tags, STANDARD_ERRORS


# ─────────────────────────────────────────────────────────────────────────────
# Response Serializers for Documentation
# ─────────────────────────────────────────────────────────────────────────────

class ContactResponseSerializer(serializers.Serializer):
    """Contact response schema for API documentation."""
    id = serializers.UUIDField(help_text="Unique contact identifier")
    fullname = serializers.CharField(help_text="Full name")
    email = serializers.EmailField(allow_blank=True, help_text="Email address")
    phone = serializers.CharField(allow_blank=True, help_text="Phone number")
    whatsapp_name = serializers.CharField(allow_blank=True, help_text="WhatsApp display name")
    company = serializers.CharField(allow_blank=True, help_text="Company name")
    source = serializers.CharField(allow_blank=True, help_text="Lead source")
    type_id = serializers.UUIDField(allow_null=True, help_text="Contact type ID")
    type_name = serializers.CharField(allow_null=True, help_text="Contact type name")
    tags = serializers.ListField(child=serializers.CharField(), help_text="Tags")
    custom_fields = serializers.DictField(help_text="Custom field values")
    is_blacklisted = serializers.BooleanField(help_text="Contact is blacklisted")
    do_not_contact = serializers.BooleanField(help_text="Contact opted out of contact")
    created_at = serializers.DateTimeField(help_text="Creation timestamp")
    updated_at = serializers.DateTimeField(help_text="Last update timestamp")


class ContactListResponseSerializer(serializers.Serializer):
    """Paginated contact list response."""
    contacts = ContactResponseSerializer(many=True)
    pagination = serializers.DictField(help_text="Pagination metadata")


class ContactPromoteResponseSerializer(serializers.Serializer):
    """Response after promoting contact to user."""
    message = serializers.CharField()
    user = serializers.DictField(help_text="Created user details")
    contact = ContactResponseSerializer(allow_null=True)


# ─────────────────────────────────────────────────────────────────────────────
# Contact Views
# ─────────────────────────────────────────────────────────────────────────────

@method_decorator(csrf_exempt, name="dispatch")
class ContactsView(ContactAPIMixin, ProtectedAPIView):
    """Contact list and creation endpoint."""

    serializer_class = ContactCreateSerializer

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

    @extend_schema(
        summary="List contacts",
        description="Retrieve a paginated list of contacts for the current tenant. Supports search, filtering by type, and sorting.",
        tags=[Tags.CRM_CONTACTS],
        parameters=[
            OpenApiParameter("search", OpenApiTypes.STR, description="Search in name, email, phone, WhatsApp name"),
            OpenApiParameter("account_id", OpenApiTypes.UUID, description="Filter by account/customer ID (contacts linked to this customer)"),
            OpenApiParameter("type", OpenApiTypes.STR, description="Filter by contact type (ID or name)"),
            OpenApiParameter("sort_by", OpenApiTypes.STR, description="Sort field: fullname, email, phone, created_at, updated_at", default="created_at"),
            OpenApiParameter("order", OpenApiTypes.STR, description="Sort order: asc or desc", default="desc"),
            OpenApiParameter("page", OpenApiTypes.INT, description="Page number", default=1),
            OpenApiParameter("limit", OpenApiTypes.INT, description="Items per page (max 100)", default=50),
        ],
        responses={
            200: ContactListResponseSerializer,
            **STANDARD_ERRORS,
        },
        examples=[
            OpenApiExample(
                "Success",
                value={
                    "contacts": [
                        {"id": "550e8400-e29b-41d4-a716-446655440000", "fullname": "John Doe", "email": "john@example.com", "phone": "+1234567890"}
                    ],
                    "pagination": {"current_page": 1, "total_pages": 5, "total_items": 100, "items_per_page": 50}
                },
                response_only=True,
            )
        ],
    )
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

    @extend_schema(
        summary="Create contact",
        description="Create a new contact for the current tenant. Emits a `contact.created` event on success.",
        tags=[Tags.CRM_CONTACTS],
        request=ContactCreateSerializer,
        responses={
            201: ContactResponseSerializer,
            **STANDARD_ERRORS,
        },
        examples=[
            OpenApiExample(
                "Create Contact",
                value={"fullname": "John Doe", "email": "john@example.com", "phone": "+1234567890", "type": "Lead"},
                request_only=True,
            )
        ],
    )
    def post(self, request):
        self._ensure_tenant_schema(request)
        tenant = getattr(request, "tenant", None) or getattr(request.user, "tenant", None)
        if not tenant:
            return Response(
                {"error": "tenant_required", "message": "Tenant context is required to create contacts."},
                status=status.HTTP_403_FORBIDDEN,
            )
        serializer = self.serializer_class(data=request.data, context={"request": request})
        try:
            serializer.is_valid(raise_exception=True)
        except ValidationError as exc:
            return Response(exc.detail, status=status.HTTP_400_BAD_REQUEST)

        with tenant_rls_context(tenant):
            contact: Contact = serializer.save(tenant=tenant, created_by=request.user)
            response_payload = serializer.data

        try:
            emit_event(
                name="contact.created",
                tenant_id=tenant.tenant_code,
                actor={"type": "user", "id": str(request.user.id)},
                entity={"type": "contact", "id": str(contact.user_id)},
                payload={
                    "contact_id": str(contact.user_id),
                    "fullname": contact.fullname,
                    "display_name": contact.display_name,
                    "whatsapp_name": contact.whatsapp_name,
                    "email": contact.email,
                    "phone": contact.phone,
                    "company": contact.company,
                    "source": contact.source,
                    "type_id": str(contact.ctype_id) if contact.ctype_id else None,
                    "type_name": contact.ctype.name if contact.ctype else None,
                    "created_at": contact.created.isoformat() if contact.created else None,
                    "updated_at": contact.updated.isoformat() if contact.updated else None,
                    "is_deleted": bool(getattr(contact, "is_deleted", False)),
                        "contact": snapshot_contact(contact),
                },
                source="api",
            )
        except Exception:
            # Do not break contact creation on event emission failures.
            pass
        if contact.is_blacklisted:
            sync_whatsapp_blocklist(contact, enabled=True)
        return Response(response_payload, status=status.HTTP_201_CREATED)


@method_decorator(csrf_exempt, name="dispatch")
class ContactDetailView(ContactAPIMixin, ProtectedAPIView):
    """Contact detail, update, and delete endpoint."""

    def _get_contact(self, request, contact_id) -> Optional[Contact]:
        tenant = getattr(request, "tenant", None) or getattr(request.user, "tenant", None)
        if tenant is None:
            return None
        return (
            Contact.objects.select_related("ctype")
            .filter(tenant=tenant, pk=contact_id)
            .first()
        )

    @extend_schema(
        summary="Get contact details",
        description="Retrieve details of a specific contact by ID.",
        tags=[Tags.CRM_CONTACTS],
        responses={200: ContactResponseSerializer, **STANDARD_ERRORS},
    )
    def get(self, request, contact_id):
        contact = self._get_contact(request, contact_id)
        if not contact:
            return _error("contact_not_found", "Contact not found", status.HTTP_404_NOT_FOUND)
        with tenant_rls_context(contact.tenant):
            payload = self._serialize_contact(contact)
        return Response(payload)

    @extend_schema(
        summary="Update contact",
        description="Partially update a contact. Fields: name, email, phone, company, type, tags, custom_fields, is_blacklisted.",
        tags=[Tags.CRM_CONTACTS],
        responses={200: ContactResponseSerializer, **STANDARD_ERRORS},
    )
    def patch(self, request, contact_id):
        payload = request.data or {}
        contact = self._get_contact(request, contact_id)
        if not contact:
            return _error("contact_not_found", "Contact not found", status.HTTP_404_NOT_FOUND)

        previous_values: dict[str, Any] = {}
        fields_to_update: list[str] = []

        if "name" in payload:
            raw_name = payload.get("name")
            name = str(raw_name).strip() if raw_name else ""
            if not name:
                return _error("invalid_request", "name cannot be empty", status.HTTP_400_BAD_REQUEST)
            previous_values["fullname"] = contact.fullname
            contact.fullname = name
            fields_to_update.append("fullname")
        if "email" in payload:
            previous_values["email"] = contact.email
            contact.email = payload.get("email", "")
            fields_to_update.append("email")
        if "phone" in payload:
            previous_values["phone"] = contact.phone
            raw_phone = payload.get("phone", "")
            contact.phone = normalize_phone_e164(raw_phone) or str(raw_phone or "")
            fields_to_update.append("phone")
        if "company" in payload:
            previous_values["company"] = contact.company
            contact.company = payload.get("company", "")
            fields_to_update.append("company")
        if "is_blacklisted" in payload:
            previous_values["is_blacklisted"] = contact.is_blacklisted
            contact.is_blacklisted = bool(payload.get("is_blacklisted"))
            fields_to_update.append("is_blacklisted")
        if "do_not_contact" in payload:
            previous_values["do_not_contact"] = contact.do_not_contact
            contact.do_not_contact = bool(payload.get("do_not_contact"))
            fields_to_update.append("do_not_contact")
        if "type" in payload:
            tenant = getattr(request, "tenant", None) or getattr(request.user, "tenant", None)
            contact_type, error = self._resolve_contact_type(tenant, payload.get("type"))
            if error:
                return _error("invalid_contact_type", error, status.HTTP_400_BAD_REQUEST)
            previous_values["ctype"] = str(contact.ctype_id) if contact.ctype_id else None
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
            with tenant_rls_context(contact.tenant):
                contact.save(update_fields=fields_to_update)
                response_payload = self._serialize_contact(contact)

            try:
                new_values: dict[str, Any] = {}
                for field in fields_to_update:
                    if field == "updated":
                        continue
                    if field == "ctype":
                        new_values["ctype"] = str(contact.ctype_id) if contact.ctype_id else None
                        new_values["ctype_name"] = contact.ctype.name if contact.ctype else None
                    else:
                        new_values[field] = getattr(contact, field, None)

                emit_event(
                    name="contact.updated",
                    tenant_id=request.user.tenant.tenant_code,
                    actor={"type": "user", "id": str(request.user.id)},
                    entity={"type": "contact", "id": str(contact.user_id)},
                    payload={
                        "contact_id": str(contact.user_id),
                        "changed_fields": [f for f in fields_to_update if f != "updated"],
                        "previous_values": previous_values,
                        "new_values": new_values,
                        "contact": snapshot_contact(contact),
                    },
                    source="api",
                )
            except Exception:
                pass
            if "is_blacklisted" in fields_to_update:
                sync_whatsapp_blocklist(contact, enabled=contact.is_blacklisted)
        else:
            with tenant_rls_context(contact.tenant):
                response_payload = self._serialize_contact(contact)
        return Response(response_payload)

    @extend_schema(
        summary="Delete contact",
        description="Permanently delete a contact. Requires tenant_admin role. Cascades to related records.",
        tags=[Tags.CRM_CONTACTS],
        responses={
            200: OpenApiResponse(description="Contact deleted successfully"),
            **STANDARD_ERRORS,
        },
    )
    def delete(self, request, contact_id):
        user = getattr(request, "user", None)
        if not user or not getattr(user, "is_authenticated", False):
            return _error("unauthenticated", "Authentication required", status.HTTP_401_UNAUTHORIZED)
        if not (getattr(user, "is_superuser", False) or user_has_role(user, "tenant_admin")):
            return _error("permission_denied", "Only tenant admins can delete contacts", status.HTTP_403_FORBIDDEN)
        contact = self._get_contact(request, contact_id)
        if not contact:
            return _error("contact_not_found", "Contact not found", status.HTTP_404_NOT_FOUND)
        with tenant_rls_context(contact.tenant):
            contact.delete()
        return Response({"message": "Contact deleted successfully"})


@method_decorator(csrf_exempt, name="dispatch")
class ContactExportView(ContactAPIMixin, ProtectedAPIView):
    """Export contacts to CSV or JSON."""

    @extend_schema(
        summary="Export contacts",
        description="Export contacts to CSV or JSON format. Returns a preview and download URL.",
        tags=[Tags.CRM_CONTACTS],
        parameters=[
            OpenApiParameter("format", OpenApiTypes.STR, description="Export format: csv or json", default="csv"),
            OpenApiParameter("type", OpenApiTypes.STR, description="Filter by contact type"),
            OpenApiParameter("tags", OpenApiTypes.STR, description="Filter by tags (comma-separated)"),
        ],
        responses={200: OpenApiResponse(description="Export details with download URL"), **STANDARD_ERRORS},
    )
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
class ContactPromoteView(ContactAPIMixin, ProtectedAPIView):
    """Promote a Contact to a User account."""

    @extend_schema(
        summary="Promote contact to user",
        description="Convert contact to user account. Requires password field. Optional: username (defaults to email).",
        tags=[Tags.CRM_CONTACTS],
        responses={201: ContactPromoteResponseSerializer, **STANDARD_ERRORS},
    )
    def post(self, request, contact_id):
        tenant = getattr(request.user, "tenant", None)
        if tenant is None:
            return _error("tenant_required", "User must belong to a tenant", status.HTTP_400_BAD_REQUEST)
        
        payload = request.data or {}
        password = payload.get("password")
        if not password:
            return _error("password_required", "Password is required", status.HTTP_400_BAD_REQUEST)
        
        username = payload.get("username")
        
        user, message = ContactService.promote_contact_to_user(
            contact_id=str(contact_id),
            tenant=tenant,
            password=password,
            username=username,
        )
        
        if user is None:
            return _error("promote_failed", message, status.HTTP_400_BAD_REQUEST)
        
        contact = Contact.objects.filter(linked_user=user, tenant=tenant).first()
        
        return Response({
            "message": message,
            "user": {
                "id": str(user.id),
                "email": user.email,
                "username": user.username,
                "first_name": user.first_name,
                "last_name": user.last_name,
            },
            "contact": self._serialize_contact(contact) if contact else None,
        }, status=status.HTTP_201_CREATED)

