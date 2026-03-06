from __future__ import annotations

import uuid
from typing import Any, Dict, Optional, Tuple

from django.db.models import Q
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.response import Response

from crm.models import ContactType
from chatbot.models.agent_configuration import AgentConfiguration
from crm.api.mixins import PaginationMixin, ProtectedAPIView, _error


@method_decorator(csrf_exempt, name="dispatch")
@extend_schema(tags=["contact-types"])
class ContactTypesView(PaginationMixin, ProtectedAPIView):
    ITEMS_KEY = "contact_types"

    def _resolve_default_agent(
        self,
        tenant,
        raw_value,
    ) -> Tuple[Optional[AgentConfiguration], Optional[Response]]:
        if raw_value in (None, ""):
            return None, None
        try:
            agent_id = uuid.UUID(str(raw_value))
        except (ValueError, TypeError):
            return None, _error("invalid_default_agent", "default_agent_id must be a valid UUID", status.HTTP_400_BAD_REQUEST)

        try:
            agent = AgentConfiguration.objects.get(tenant=tenant, id=agent_id)
        except AgentConfiguration.DoesNotExist:
            return None, _error("default_agent_not_found", "Default agent not found", status.HTTP_404_NOT_FOUND)
        return agent, None

    def _serialize_contact_type(self, contact_type: ContactType) -> Dict[str, Any]:
        return {
            "id": str(contact_type.pk),
            "name": contact_type.name,
            "description": contact_type.description,
            "color": contact_type.color,
            "name_label": contact_type.get_name_display(),
            "default_agent_id": str(contact_type.default_agent_id) if contact_type.default_agent_id else None,
        }

    def _base_queryset(self, request):
        tenant = self._get_tenant_or_none(request)
        if tenant is None:
            return ContactType.objects.none()
        return ContactType.objects.filter(tenant=tenant).select_related("default_agent")

    def get(self, request):
        queryset = self._base_queryset(request)

        search = (request.query_params.get("search") or "").strip()
        if search:
            queryset = queryset.filter(name__icontains=search)

        sort_by = request.query_params.get("sort_by", "name")
        order = request.query_params.get("order", "asc")
        prefix = "-" if order == "desc" else ""

        allowed_sort_fields = {"name"}
        if sort_by not in allowed_sort_fields:
            sort_by = "name"

        queryset = queryset.order_by(f"{prefix}{sort_by}")
        return Response(self._paginate(queryset, request, self._serialize_contact_type, "contact_types"))

    def post(self, request):
        tenant = self._get_tenant_or_none(request)
        if tenant is None:
            return _error("tenant_required", "User must belong to a tenant", status.HTTP_400_BAD_REQUEST)

        payload = request.data or {}
        name = (payload.get("name") or "").strip()
        if not name:
            return _error("invalid_request", "name is required", status.HTTP_400_BAD_REQUEST)

        if ContactType.objects.filter(tenant=tenant, name__iexact=name).exists():
            return _error("duplicate_name", "Contact type with this name already exists", status.HTTP_409_CONFLICT)

        default_agent, error = self._resolve_default_agent(tenant, payload.get("default_agent_id"))
        if error:
            return error

        contact_type = ContactType.objects.create(
            tenant=tenant,
            name=name,
            description=payload.get("description") or "",
            color=payload.get("color") or "",
            default_agent=default_agent,
        )
        return Response(self._serialize_contact_type(contact_type), status=status.HTTP_201_CREATED)


@method_decorator(csrf_exempt, name="dispatch")
@extend_schema(tags=["contact-types"])
class ContactTypeDetailView(PaginationMixin, ProtectedAPIView):
    def _resolve_default_agent(
        self,
        tenant,
        raw_value,
    ) -> Tuple[Optional[AgentConfiguration], Optional[Response]]:
        if raw_value in (None, ""):
            return None, None
        try:
            agent_id = uuid.UUID(str(raw_value))
        except (ValueError, TypeError):
            return None, _error("invalid_default_agent", "default_agent_id must be a valid UUID", status.HTTP_400_BAD_REQUEST)

        try:
            agent = AgentConfiguration.objects.get(tenant=tenant, id=agent_id)
        except AgentConfiguration.DoesNotExist:
            return None, _error("default_agent_not_found", "Default agent not found", status.HTTP_404_NOT_FOUND)
        return agent, None

    def _get_contact_type(self, request, contact_type_id) -> Optional[ContactType]:
        tenant = self._get_tenant_or_none(request)
        if tenant is None:
            return None
        try:
            return ContactType.objects.filter(tenant=tenant).select_related("default_agent").get(pk=contact_type_id)
        except ContactType.DoesNotExist:
            return None

    def _serialize_contact_type(self, contact_type: ContactType) -> Dict[str, Any]:
        return {
            "id": str(contact_type.pk),
            "name": contact_type.name,
            "description": contact_type.description,
            "color": contact_type.color,
            "name_label": contact_type.get_name_display(),
            "default_agent_id": str(contact_type.default_agent_id) if contact_type.default_agent_id else None,
        }

    def get(self, request, contact_type_id):
        contact_type = self._get_contact_type(request, contact_type_id)
        if not contact_type:
            return _error("contact_type_not_found", "Contact type not found", status.HTTP_404_NOT_FOUND)
        return Response(self._serialize_contact_type(contact_type))

    def patch(self, request, contact_type_id):
        contact_type = self._get_contact_type(request, contact_type_id)
        if not contact_type:
            return _error("contact_type_not_found", "Contact type not found", status.HTTP_404_NOT_FOUND)

        payload = request.data or {}
        if "name" in payload:
            new_name = (payload.get("name") or "").strip()
            if not new_name:
                return _error("invalid_request", "name cannot be empty", status.HTTP_400_BAD_REQUEST)
            if ContactType.objects.filter(tenant=contact_type.tenant, name__iexact=new_name).exclude(pk=contact_type.pk).exists():
                return _error("duplicate_name", "Contact type with this name already exists", status.HTTP_409_CONFLICT)
            contact_type.name = new_name

        if "description" in payload:
            contact_type.description = payload.get("description") or ""

        if "color" in payload:
            contact_type.color = payload.get("color") or ""

        if "default_agent_id" in payload:
            default_agent, error = self._resolve_default_agent(contact_type.tenant, payload.get("default_agent_id"))
            if error:
                return error
            contact_type.default_agent = default_agent

        contact_type.save()
        return Response(self._serialize_contact_type(contact_type))

    def delete(self, request, contact_type_id):
        contact_type = self._get_contact_type(request, contact_type_id)
        if not contact_type:
            return _error("contact_type_not_found", "Contact type not found", status.HTTP_404_NOT_FOUND)
        contact_type.delete()
        return Response({"message": "Contact type deleted successfully"})
