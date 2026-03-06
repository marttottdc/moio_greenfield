from __future__ import annotations

from typing import Any, Dict, Optional

from django.db.models import Q
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.response import Response

from crm.models import Product
from crm.api.mixins import PaginationMixin, ProtectedAPIView, _error


@method_decorator(csrf_exempt, name="dispatch")
@extend_schema(tags=["products"])
class ProductsView(PaginationMixin, ProtectedAPIView):
    ITEMS_KEY = "products"

    def _serialize_product(self, product: Product) -> Dict[str, Any]:
        tags = list(product.tags.values_list("name", flat=True)) if product.tags.exists() else []
        return {
            "id": str(product.pk),
            "name": product.name,
            "description": product.description,
            "price": product.price,
            "sale_price": product.sale_price,
            "price_currency": product.price_currency,
            "brand": product.brand,
            "category": product.category,
            "sku": product.sku,
            "product_type": product.product_type,
            "product_type_label": product.get_product_type_display(),
            "attributes": product.attributes,
            "tags": tags,
            "permalink": product.permalink,
            "main_image": product.main_image,
            "fb_product_id": product.fb_product_id,
            "frontend_product_id": product.frontend_product_id,
            "created_at": self._isoformat(product.created_at),
        }

    def _base_queryset(self, request):
        tenant = self._get_tenant_or_none(request)
        if tenant is None:
            return Product.objects.none()
        return Product.objects.filter(tenant=tenant).prefetch_related("tags")

    def get(self, request):
        queryset = self._base_queryset(request)

        search = (request.query_params.get("search") or "").strip()
        if search:
            queryset = queryset.filter(
                Q(name__icontains=search)
                | Q(description__icontains=search)
                | Q(brand__icontains=search)
                | Q(category__icontains=search)
                | Q(sku__icontains=search)
            )

        category_filter = request.query_params.get("category")
        if category_filter:
            queryset = queryset.filter(category=category_filter)

        brand_filter = request.query_params.get("brand")
        if brand_filter:
            queryset = queryset.filter(brand=brand_filter)

        product_type_filter = request.query_params.get("product_type")
        if product_type_filter:
            queryset = queryset.filter(product_type=product_type_filter)

        sort_by = request.query_params.get("sort_by", "created_at")
        order = request.query_params.get("order", "desc")
        prefix = "-" if order == "desc" else ""

        allowed_sort_fields = {"created_at", "name", "price", "sale_price", "category", "brand"}
        if sort_by not in allowed_sort_fields:
            sort_by = "created_at"

        queryset = queryset.order_by(f"{prefix}{sort_by}")
        return Response(self._paginate(queryset, request, self._serialize_product, "products"))

    def post(self, request):
        tenant = self._get_tenant_or_none(request)
        if tenant is None:
            return _error("tenant_required", "User must belong to a tenant", status.HTTP_400_BAD_REQUEST)

        payload = request.data or {}
        name = (payload.get("name") or "").strip()
        if not name:
            return _error("invalid_request", "name is required", status.HTTP_400_BAD_REQUEST)

        product = Product(
            tenant=tenant,
            name=name,
            description=payload.get("description", ""),
            price=payload.get("price", 0),
            sale_price=payload.get("sale_price", 0),
            price_currency=payload.get("price_currency"),
            brand=payload.get("brand"),
            category=payload.get("category"),
            sku=payload.get("sku"),
            product_type=payload.get("product_type", "STD"),
            attributes=payload.get("attributes", {}),
            permalink=payload.get("permalink"),
            main_image=payload.get("main_image"),
            frontend_product_id=payload.get("frontend_product_id"),
        )
        product.save()
        return Response(self._serialize_product(product), status=status.HTTP_201_CREATED)


@method_decorator(csrf_exempt, name="dispatch")
@extend_schema(tags=["products"])
class ProductDetailView(PaginationMixin, ProtectedAPIView):

    def _get_product(self, request, product_id) -> Optional[Product]:
        tenant = self._get_tenant_or_none(request)
        if tenant is None:
            return None
        try:
            return Product.objects.filter(tenant=tenant).prefetch_related("tags").get(pk=product_id)
        except Product.DoesNotExist:
            return None

    def _serialize_product(self, product: Product) -> Dict[str, Any]:
        tags = list(product.tags.values_list("name", flat=True)) if product.tags.exists() else []
        return {
            "id": str(product.pk),
            "name": product.name,
            "description": product.description,
            "price": product.price,
            "sale_price": product.sale_price,
            "price_currency": product.price_currency,
            "brand": product.brand,
            "category": product.category,
            "sku": product.sku,
            "product_type": product.product_type,
            "product_type_label": product.get_product_type_display(),
            "attributes": product.attributes,
            "tags": tags,
            "permalink": product.permalink,
            "main_image": product.main_image,
            "fb_product_id": product.fb_product_id,
            "frontend_product_id": product.frontend_product_id,
            "created_at": self._isoformat(product.created_at),
        }

    def get(self, request, product_id):
        product = self._get_product(request, product_id)
        if not product:
            return _error("product_not_found", "Product not found", status.HTTP_404_NOT_FOUND)
        return Response(self._serialize_product(product))

    def patch(self, request, product_id):
        product = self._get_product(request, product_id)
        if not product:
            return _error("product_not_found", "Product not found", status.HTTP_404_NOT_FOUND)

        payload = request.data or {}
        updatable_fields = [
            "name", "description", "price", "sale_price", "price_currency",
            "brand", "category", "sku", "product_type", "attributes",
            "permalink", "main_image", "frontend_product_id"
        ]

        for field in updatable_fields:
            if field in payload:
                setattr(product, field, payload[field])

        product.save()
        return Response(self._serialize_product(product))

    def delete(self, request, product_id):
        product = self._get_product(request, product_id)
        if not product:
            return _error("product_not_found", "Product not found", status.HTTP_404_NOT_FOUND)
        product.delete()
        return Response({"message": "Product deleted successfully"})
