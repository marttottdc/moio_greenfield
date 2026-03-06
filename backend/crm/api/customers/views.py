from __future__ import annotations

from typing import Any, Dict, Optional

from django.db.models import Q
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.response import Response

from crm.models import Customer, Address
from crm.api.mixins import PaginationMixin, ProtectedAPIView, _error


@method_decorator(csrf_exempt, name="dispatch")
@extend_schema(tags=["customers"])
class CustomersView(PaginationMixin, ProtectedAPIView):
    ITEMS_KEY = "customers"

    def _serialize_address(self, address: Address) -> Dict[str, Any]:
        return {
            "id": address.pk,
            "name": address.name,
            "address": address.address,
            "address_internal": address.address_internal,
            "city": address.city,
            "state": address.state,
            "country": address.country,
            "postalcode": address.postalcode,
            "latitude": float(address.latitude) if address.latitude else None,
            "longitude": float(address.longitude) if address.longitude else None,
            "type_location": address.type_location,
            "comments": address.comments,
            "invoice_address": address.invoice_address,
            "delivery_address": address.delivery_address,
            "enabled": address.enabled,
        }

    def _serialize_customer(self, customer: Customer) -> Dict[str, Any]:
        addresses = customer.address.all() if hasattr(customer, 'address') else []
        return {
            "id": str(customer.pk),
            "name": customer.name,
            "legal_name": customer.legal_name,
            "type": customer.type,
            "status": customer.status,
            "enabled": customer.enabled,
            "tax_id": customer.tax_id,
            "first_name": customer.first_name,
            "last_name": customer.last_name,
            "date_of_birth": customer.date_of_birth.isoformat() if customer.date_of_birth else None,
            "national_document": customer.national_document,
            "passport": customer.passport,
            "gender": customer.gender,
            "phone": customer.phone,
            "email": customer.email,
            "external_id": customer.external_id,
            "addresses": [self._serialize_address(addr) for addr in addresses],
            "created_at": self._isoformat(customer.created),
        }

    def _base_queryset(self, request):
        tenant = self._get_tenant_or_none(request)
        if tenant is None:
            return Customer.objects.none()
        return Customer.objects.filter(tenant=tenant).prefetch_related("address")

    def get(self, request):
        queryset = self._base_queryset(request)

        search = (request.query_params.get("search") or "").strip()
        if search:
            queryset = queryset.filter(
                Q(name__icontains=search)
                | Q(legal_name__icontains=search)
                | Q(email__icontains=search)
                | Q(phone__icontains=search)
                | Q(tax_id__icontains=search)
            )

        type_filter = request.query_params.get("type")
        if type_filter:
            queryset = queryset.filter(type=type_filter)

        enabled_filter = request.query_params.get("enabled")
        if enabled_filter is not None:
            queryset = queryset.filter(enabled=enabled_filter.lower() == "true")

        sort_by = request.query_params.get("sort_by", "created")
        order = request.query_params.get("order", "desc")
        prefix = "-" if order == "desc" else ""

        allowed_sort_fields = {"created", "name", "legal_name", "email", "type"}
        if sort_by not in allowed_sort_fields:
            sort_by = "created"

        queryset = queryset.order_by(f"{prefix}{sort_by}")
        return Response(self._paginate(queryset, request, self._serialize_customer, "customers"))

    def post(self, request):
        tenant = self._get_tenant_or_none(request)
        if tenant is None:
            return _error("tenant_required", "User must belong to a tenant", status.HTTP_400_BAD_REQUEST)

        payload = request.data or {}
        name = (payload.get("name") or "").strip()
        if not name:
            return _error("invalid_request", "name is required", status.HTTP_400_BAD_REQUEST)

        customer = Customer.objects.create(
            tenant=tenant,
            name=name,
            legal_name=payload.get("legal_name") or name,
            type=payload.get("type", Customer.PERSON),
            status=payload.get("status", ""),
            enabled=payload.get("enabled", True),
            tax_id=payload.get("tax_id"),
            first_name=payload.get("first_name", ""),
            last_name=payload.get("last_name", ""),
            date_of_birth=payload.get("date_of_birth"),
            national_document=payload.get("national_document"),
            passport=payload.get("passport"),
            gender=payload.get("gender"),
            phone=payload.get("phone"),
            email=payload.get("email"),
            external_id=payload.get("external_id"),
        )
        return Response(self._serialize_customer(customer), status=status.HTTP_201_CREATED)


@method_decorator(csrf_exempt, name="dispatch")
@extend_schema(tags=["customers"])
class CustomerDetailView(PaginationMixin, ProtectedAPIView):

    def _get_customer(self, request, customer_id) -> Optional[Customer]:
        tenant = self._get_tenant_or_none(request)
        if tenant is None:
            return None
        try:
            return Customer.objects.filter(tenant=tenant).prefetch_related("address").get(pk=customer_id)
        except Customer.DoesNotExist:
            return None

    def _serialize_customer(self, customer: Customer) -> Dict[str, Any]:
        addresses = customer.address.all() if hasattr(customer, 'address') else []
        return {
            "id": str(customer.pk),
            "name": customer.name,
            "legal_name": customer.legal_name,
            "type": customer.type,
            "status": customer.status,
            "enabled": customer.enabled,
            "tax_id": customer.tax_id,
            "first_name": customer.first_name,
            "last_name": customer.last_name,
            "date_of_birth": customer.date_of_birth.isoformat() if customer.date_of_birth else None,
            "national_document": customer.national_document,
            "passport": customer.passport,
            "gender": customer.gender,
            "phone": customer.phone,
            "email": customer.email,
            "external_id": customer.external_id,
            "addresses": [
                {
                    "id": addr.pk,
                    "name": addr.name,
                    "address": addr.address,
                    "city": addr.city,
                    "state": addr.state,
                    "country": addr.country,
                    "postalcode": addr.postalcode,
                }
                for addr in addresses
            ],
            "created_at": self._isoformat(customer.created),
        }

    def get(self, request, customer_id):
        customer = self._get_customer(request, customer_id)
        if not customer:
            return _error("customer_not_found", "Customer not found", status.HTTP_404_NOT_FOUND)
        return Response(self._serialize_customer(customer))

    def patch(self, request, customer_id):
        customer = self._get_customer(request, customer_id)
        if not customer:
            return _error("customer_not_found", "Customer not found", status.HTTP_404_NOT_FOUND)

        payload = request.data or {}
        updatable_fields = [
            "name", "legal_name", "type", "status", "enabled", "tax_id",
            "first_name", "last_name", "date_of_birth", "national_document",
            "passport", "gender", "phone", "email", "external_id"
        ]

        for field in updatable_fields:
            if field in payload:
                setattr(customer, field, payload[field])

        customer.save()
        return Response(self._serialize_customer(customer))

    def delete(self, request, customer_id):
        customer = self._get_customer(request, customer_id)
        if not customer:
            return _error("customer_not_found", "Customer not found", status.HTTP_404_NOT_FOUND)
        customer.delete()
        return Response({"message": "Customer deleted successfully"})
