from __future__ import annotations

import uuid
from typing import Any, Dict

from django.db import transaction
from django.db.models import Count, Min, Max, Sum, Prefetch
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.authentication import JWTAuthentication

from portal.authentication import CsrfExemptSessionAuthentication, TenantJWTAAuthentication

from . import models, serializers


class AuthenticatedAPIView(APIView):
    authentication_classes = [
        CsrfExemptSessionAuthentication,
        TenantJWTAAuthentication,
        JWTAuthentication,
    ]
    permission_classes = [IsAuthenticated]

    def get_tenant(self, request):
        tenant = getattr(request.user, "tenant", None)
        if tenant is None:
            from rest_framework.exceptions import ValidationError
            raise ValidationError("Authenticated user must belong to a tenant")
        return tenant


class BrandListView(AuthenticatedAPIView):
    def get(self, request):
        tenant = self.get_tenant(request)
        brands = models.Brand.objects.filter(tenant=tenant).order_by("name")
        
        is_active = request.query_params.get("is_active")
        if is_active is not None:
            brands = brands.filter(is_active=is_active.lower() == "true")
        
        serializer = serializers.BrandSerializer(brands, many=True)
        return Response({"brands": serializer.data})

    def post(self, request):
        tenant = self.get_tenant(request)
        serializer = serializers.BrandSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save(tenant=tenant)
        return Response(serializer.data, status=status.HTTP_201_CREATED)


class BrandDetailView(AuthenticatedAPIView):
    def get(self, request, brand_id: str):
        tenant = self.get_tenant(request)
        brand = get_object_or_404(models.Brand, tenant=tenant, id=brand_id)
        serializer = serializers.BrandSerializer(brand)
        return Response(serializer.data)

    def put(self, request, brand_id: str):
        tenant = self.get_tenant(request)
        brand = get_object_or_404(models.Brand, tenant=tenant, id=brand_id)
        serializer = serializers.BrandSerializer(brand, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)

    def delete(self, request, brand_id: str):
        tenant = self.get_tenant(request)
        brand = get_object_or_404(models.Brand, tenant=tenant, id=brand_id)
        brand.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class CategoryListView(AuthenticatedAPIView):
    def get(self, request):
        tenant = self.get_tenant(request)
        categories = models.Category.objects.filter(tenant=tenant)
        
        is_active = request.query_params.get("is_active")
        if is_active is not None:
            categories = categories.filter(is_active=is_active.lower() == "true")
        
        parent_id = request.query_params.get("parent_id")
        if parent_id == "null" or parent_id == "":
            categories = categories.filter(parent__isnull=True)
        elif parent_id:
            categories = categories.filter(parent_id=parent_id)
        
        tree = request.query_params.get("tree")
        if tree and tree.lower() == "true":
            root_categories = categories.filter(parent__isnull=True).order_by("order", "name")
            serializer = serializers.CategoryTreeSerializer(root_categories, many=True)
            return Response({"categories": serializer.data})
        
        categories = categories.annotate(_children_count=Count("children")).order_by("path", "order")
        serializer = serializers.CategorySerializer(categories, many=True)
        return Response({"categories": serializer.data})

    def post(self, request):
        tenant = self.get_tenant(request)
        serializer = serializers.CategorySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        parent_id = request.data.get("parent_id")
        parent = None
        if parent_id:
            parent = get_object_or_404(models.Category, tenant=tenant, id=parent_id)
        
        serializer.save(tenant=tenant, parent=parent)
        return Response(serializer.data, status=status.HTTP_201_CREATED)


class CategoryDetailView(AuthenticatedAPIView):
    def get(self, request, category_id: str):
        tenant = self.get_tenant(request)
        category = get_object_or_404(
            models.Category.objects.annotate(_children_count=Count("children")),
            tenant=tenant,
            id=category_id,
        )
        serializer = serializers.CategorySerializer(category)
        return Response(serializer.data)

    def put(self, request, category_id: str):
        tenant = self.get_tenant(request)
        category = get_object_or_404(models.Category, tenant=tenant, id=category_id)
        serializer = serializers.CategorySerializer(category, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        
        parent_id = request.data.get("parent_id")
        if parent_id is not None:
            if parent_id == "" or parent_id == "null":
                serializer.save(parent=None)
            else:
                parent = get_object_or_404(models.Category, tenant=tenant, id=parent_id)
                serializer.save(parent=parent)
        else:
            serializer.save()
        
        return Response(serializer.data)

    def delete(self, request, category_id: str):
        tenant = self.get_tenant(request)
        category = get_object_or_404(models.Category, tenant=tenant, id=category_id)
        category.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class AttributeDefinitionListView(AuthenticatedAPIView):
    def get(self, request):
        tenant = self.get_tenant(request)
        attributes = models.AttributeDefinition.objects.filter(tenant=tenant)
        
        is_variant = request.query_params.get("is_variant_attribute")
        if is_variant is not None:
            attributes = attributes.filter(is_variant_attribute=is_variant.lower() == "true")
        
        is_filterable = request.query_params.get("is_filterable")
        if is_filterable is not None:
            attributes = attributes.filter(is_filterable=is_filterable.lower() == "true")
        
        attributes = attributes.annotate(_options_count=Count("options")).order_by("order", "name")
        serializer = serializers.AttributeDefinitionListSerializer(attributes, many=True)
        return Response({"attributes": serializer.data})

    def post(self, request):
        tenant = self.get_tenant(request)
        serializer = serializers.AttributeDefinitionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save(tenant=tenant)
        return Response(serializer.data, status=status.HTTP_201_CREATED)


class AttributeDefinitionDetailView(AuthenticatedAPIView):
    def get(self, request, attribute_id: str):
        tenant = self.get_tenant(request)
        attribute = get_object_or_404(
            models.AttributeDefinition.objects.prefetch_related("options"),
            tenant=tenant,
            id=attribute_id,
        )
        serializer = serializers.AttributeDefinitionSerializer(attribute)
        return Response(serializer.data)

    def put(self, request, attribute_id: str):
        tenant = self.get_tenant(request)
        attribute = get_object_or_404(models.AttributeDefinition, tenant=tenant, id=attribute_id)
        serializer = serializers.AttributeDefinitionSerializer(attribute, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)

    def delete(self, request, attribute_id: str):
        tenant = self.get_tenant(request)
        attribute = get_object_or_404(models.AttributeDefinition, tenant=tenant, id=attribute_id)
        attribute.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class AttributeOptionListView(AuthenticatedAPIView):
    def get(self, request, attribute_id: str):
        tenant = self.get_tenant(request)
        attribute = get_object_or_404(models.AttributeDefinition, tenant=tenant, id=attribute_id)
        options = attribute.options.all().order_by("order", "value")
        serializer = serializers.AttributeOptionSerializer(options, many=True)
        return Response({"options": serializer.data})

    def post(self, request, attribute_id: str):
        tenant = self.get_tenant(request)
        attribute = get_object_or_404(models.AttributeDefinition, tenant=tenant, id=attribute_id)
        serializer = serializers.AttributeOptionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save(attribute=attribute)
        return Response(serializer.data, status=status.HTTP_201_CREATED)


class AttributeOptionDetailView(AuthenticatedAPIView):
    def put(self, request, attribute_id: str, option_id: str):
        tenant = self.get_tenant(request)
        attribute = get_object_or_404(models.AttributeDefinition, tenant=tenant, id=attribute_id)
        option = get_object_or_404(models.AttributeOption, attribute=attribute, id=option_id)
        serializer = serializers.AttributeOptionSerializer(option, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)

    def delete(self, request, attribute_id: str, option_id: str):
        tenant = self.get_tenant(request)
        attribute = get_object_or_404(models.AttributeDefinition, tenant=tenant, id=attribute_id)
        option = get_object_or_404(models.AttributeOption, attribute=attribute, id=option_id)
        option.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class ProductListView(AuthenticatedAPIView):
    def get(self, request):
        tenant = self.get_tenant(request)
        products = models.Product.objects.filter(tenant=tenant).select_related("brand", "category")
        
        status_filter = request.query_params.get("status")
        if status_filter:
            products = products.filter(status=status_filter)
        
        category_id = request.query_params.get("category_id")
        if category_id:
            products = products.filter(category_id=category_id)
        
        brand_id = request.query_params.get("brand_id")
        if brand_id:
            products = products.filter(brand_id=brand_id)
        
        search = request.query_params.get("search")
        if search:
            products = products.filter(name__icontains=search)
        
        products = products.annotate(
            _variants_count=Count("variants"),
            _total_stock=Sum("variants__stock_quantity"),
        ).order_by("-created_at")
        
        serializer = serializers.ProductListSerializer(products, many=True)
        return Response({"products": serializer.data})

    def post(self, request):
        tenant = self.get_tenant(request)
        serializer = serializers.ProductSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save(tenant=tenant)
        return Response(serializer.data, status=status.HTTP_201_CREATED)


class ProductDetailView(AuthenticatedAPIView):
    def get(self, request, product_id: str):
        tenant = self.get_tenant(request)
        product = get_object_or_404(
            models.Product.objects.select_related("brand", "category")
            .prefetch_related(
                Prefetch(
                    "variants",
                    queryset=models.ProductVariant.objects.filter(is_active=True)
                    .prefetch_related("attributes__attribute", "attributes__option", "media")
                    .order_by("position"),
                ),
                Prefetch(
                    "media",
                    queryset=models.ProductMedia.objects.order_by("position"),
                ),
                Prefetch(
                    "attributes",
                    queryset=models.ProductAttribute.objects.select_related("attribute", "value_option"),
                ),
            ),
            tenant=tenant,
            id=product_id,
        )
        serializer = serializers.ProductSerializer(product)
        return Response(serializer.data)

    def put(self, request, product_id: str):
        tenant = self.get_tenant(request)
        product = get_object_or_404(models.Product, tenant=tenant, id=product_id)
        serializer = serializers.ProductSerializer(product, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)

    def delete(self, request, product_id: str):
        tenant = self.get_tenant(request)
        product = get_object_or_404(models.Product, tenant=tenant, id=product_id)
        product.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class ProductVariantListView(AuthenticatedAPIView):
    def get(self, request, product_id: str):
        tenant = self.get_tenant(request)
        product = get_object_or_404(models.Product, tenant=tenant, id=product_id)
        variants = product.variants.prefetch_related(
            "attributes__attribute", "attributes__option", "media"
        ).order_by("position")
        serializer = serializers.ProductVariantSerializer(variants, many=True)
        return Response({"variants": serializer.data})

    def post(self, request, product_id: str):
        tenant = self.get_tenant(request)
        product = get_object_or_404(models.Product, tenant=tenant, id=product_id)
        serializer = serializers.ProductVariantSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save(tenant=tenant, product=product)
        return Response(serializer.data, status=status.HTTP_201_CREATED)


class ProductVariantDetailView(AuthenticatedAPIView):
    def get(self, request, product_id: str, variant_id: str):
        tenant = self.get_tenant(request)
        product = get_object_or_404(models.Product, tenant=tenant, id=product_id)
        variant = get_object_or_404(
            product.variants.prefetch_related("attributes__attribute", "attributes__option", "media"),
            id=variant_id,
        )
        serializer = serializers.ProductVariantSerializer(variant)
        return Response(serializer.data)

    def put(self, request, product_id: str, variant_id: str):
        tenant = self.get_tenant(request)
        product = get_object_or_404(models.Product, tenant=tenant, id=product_id)
        variant = get_object_or_404(product.variants, id=variant_id)
        serializer = serializers.ProductVariantSerializer(variant, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)

    def delete(self, request, product_id: str, variant_id: str):
        tenant = self.get_tenant(request)
        product = get_object_or_404(models.Product, tenant=tenant, id=product_id)
        variant = get_object_or_404(product.variants, id=variant_id)
        variant.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class ProductMediaListView(AuthenticatedAPIView):
    def get(self, request, product_id: str):
        tenant = self.get_tenant(request)
        product = get_object_or_404(models.Product, tenant=tenant, id=product_id)
        media = product.media.order_by("position")
        serializer = serializers.ProductMediaSerializer(media, many=True)
        return Response({"media": serializer.data})

    def post(self, request, product_id: str):
        tenant = self.get_tenant(request)
        product = get_object_or_404(models.Product, tenant=tenant, id=product_id)
        serializer = serializers.ProductMediaSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save(tenant=tenant, product=product)
        return Response(serializer.data, status=status.HTTP_201_CREATED)


class ProductMediaDetailView(AuthenticatedAPIView):
    def put(self, request, product_id: str, media_id: str):
        tenant = self.get_tenant(request)
        product = get_object_or_404(models.Product, tenant=tenant, id=product_id)
        media = get_object_or_404(product.media, id=media_id)
        serializer = serializers.ProductMediaSerializer(media, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)

    def delete(self, request, product_id: str, media_id: str):
        tenant = self.get_tenant(request)
        product = get_object_or_404(models.Product, tenant=tenant, id=product_id)
        media = get_object_or_404(product.media, id=media_id)
        media.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class OrderListView(AuthenticatedAPIView):
    def get(self, request):
        tenant = self.get_tenant(request)
        orders = models.Order.objects.filter(tenant=tenant)
        
        status_filter = request.query_params.get("status")
        if status_filter:
            orders = orders.filter(status=status_filter)
        
        payment_status = request.query_params.get("payment_status")
        if payment_status:
            orders = orders.filter(payment_status=payment_status)
        
        customer_email = request.query_params.get("customer_email")
        if customer_email:
            orders = orders.filter(customer_email__icontains=customer_email)
        
        orders = orders.annotate(_lines_count=Count("lines")).order_by("-created_at")
        serializer = serializers.OrderListSerializer(orders, many=True)
        return Response({"orders": serializer.data})

    def post(self, request):
        tenant = self.get_tenant(request)
        create_serializer = serializers.OrderCreateSerializer(data=request.data)
        create_serializer.is_valid(raise_exception=True)
        data = create_serializer.validated_data
        
        with transaction.atomic():
            order = models.Order.objects.create(
                tenant=tenant,
                order_number=f"ORD-{uuid.uuid4().hex[:8].upper()}",
                customer_email=data["customer_email"],
                customer_name=data["customer_name"],
                customer_phone=data.get("customer_phone", ""),
                shipping_address=data.get("shipping_address", {}),
                billing_address=data.get("billing_address", {}),
                notes=data.get("notes", ""),
                currency=data.get("currency", "USD"),
            )
            
            for line_data in data["lines"]:
                variant = get_object_or_404(
                    models.ProductVariant.objects.select_for_update(),
                    tenant=tenant,
                    id=line_data["variant_id"],
                )
                quantity = int(line_data["quantity"])
                unit_price = line_data.get("unit_price", variant.effective_price)
                
                if variant.track_inventory and not variant.allow_backorder:
                    if variant.stock_quantity < quantity:
                        from rest_framework.exceptions import ValidationError
                        raise ValidationError(
                            f"Insufficient stock for {variant.sku}. Available: {variant.stock_quantity}"
                        )
                    variant.stock_quantity -= quantity
                    variant.save(update_fields=["stock_quantity", "updated_at"])
                
                models.OrderLine.objects.create(
                    order=order,
                    variant=variant,
                    product_name=variant.product.name,
                    variant_name=variant.name,
                    sku=variant.sku,
                    quantity=quantity,
                    unit_price=unit_price,
                    discount_amount=line_data.get("discount_amount", 0),
                    tax_amount=line_data.get("tax_amount", 0),
                    total=(unit_price * quantity),
                )
            
            order.calculate_totals()
        
        serializer = serializers.OrderSerializer(order)
        return Response(serializer.data, status=status.HTTP_201_CREATED)


class OrderDetailView(AuthenticatedAPIView):
    def get(self, request, order_id: str):
        tenant = self.get_tenant(request)
        order = get_object_or_404(
            models.Order.objects.prefetch_related(
                Prefetch("lines", queryset=models.OrderLine.objects.select_related("variant"))
            ).select_related("contact"),
            tenant=tenant,
            id=order_id,
        )
        serializer = serializers.OrderSerializer(order)
        return Response(serializer.data)

    def put(self, request, order_id: str):
        tenant = self.get_tenant(request)
        order = get_object_or_404(models.Order, tenant=tenant, id=order_id)
        serializer = serializers.OrderSerializer(order, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)


class OrderActionView(AuthenticatedAPIView):
    def post(self, request, order_id: str, action: str):
        tenant = self.get_tenant(request)
        order = get_object_or_404(models.Order, tenant=tenant, id=order_id)
        
        if action == "confirm":
            order.confirm()
        elif action == "ship":
            order.ship()
        elif action == "deliver":
            order.deliver()
        elif action == "cancel":
            reason = request.data.get("reason", "")
            order.cancel(reason=reason)
        else:
            from rest_framework.exceptions import ValidationError
            raise ValidationError(f"Unknown action: {action}")
        
        serializer = serializers.OrderSerializer(order)
        return Response(serializer.data)
