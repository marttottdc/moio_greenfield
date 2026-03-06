from __future__ import annotations

from decimal import Decimal
from typing import Any, Dict, List

from rest_framework import serializers

from .models import (
    AttributeDefinition,
    AttributeOption,
    Brand,
    Category,
    Order,
    OrderLine,
    Product,
    ProductAttribute,
    ProductMedia,
    ProductVariant,
    VariantAttribute,
)


class BrandSerializer(serializers.ModelSerializer):
    class Meta:
        model = Brand
        fields = [
            "id",
            "name",
            "slug",
            "description",
            "logo_url",
            "website_url",
            "is_active",
            "metadata",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]


class CategorySerializer(serializers.ModelSerializer):
    parent_id = serializers.UUIDField(required=False, allow_null=True, write_only=True)
    parent_name = serializers.CharField(source="parent.name", read_only=True)
    children_count = serializers.SerializerMethodField()

    class Meta:
        model = Category
        fields = [
            "id",
            "name",
            "slug",
            "description",
            "parent_id",
            "parent_name",
            "image_url",
            "order",
            "is_active",
            "path",
            "depth",
            "children_count",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "path", "depth", "created_at", "updated_at"]

    def get_children_count(self, obj: Category) -> int:
        if hasattr(obj, "_children_count"):
            return obj._children_count
        return obj.children.count()


class CategoryTreeSerializer(serializers.ModelSerializer):
    children = serializers.SerializerMethodField()

    class Meta:
        model = Category
        fields = ["id", "name", "slug", "is_active", "order", "depth", "children"]

    def get_children(self, obj: Category) -> List[Dict[str, Any]]:
        children = getattr(obj, "_prefetched_children", None)
        if children is None:
            children = obj.children.filter(is_active=True).order_by("order", "name")
        return CategoryTreeSerializer(children, many=True).data


class AttributeOptionSerializer(serializers.ModelSerializer):
    class Meta:
        model = AttributeOption
        fields = ["id", "value", "label", "color_hex", "order"]
        read_only_fields = ["id"]


class AttributeDefinitionSerializer(serializers.ModelSerializer):
    options = AttributeOptionSerializer(many=True, read_only=True)

    class Meta:
        model = AttributeDefinition
        fields = [
            "id",
            "name",
            "slug",
            "attribute_type",
            "is_variant_attribute",
            "is_filterable",
            "is_required",
            "order",
            "options",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]


class AttributeDefinitionListSerializer(serializers.ModelSerializer):
    options_count = serializers.SerializerMethodField()

    class Meta:
        model = AttributeDefinition
        fields = [
            "id",
            "name",
            "slug",
            "attribute_type",
            "is_variant_attribute",
            "is_filterable",
            "is_required",
            "order",
            "options_count",
        ]

    def get_options_count(self, obj: AttributeDefinition) -> int:
        if hasattr(obj, "_options_count"):
            return obj._options_count
        return obj.options.count()


class VariantAttributeSerializer(serializers.ModelSerializer):
    attribute_name = serializers.CharField(source="attribute.name", read_only=True)
    attribute_slug = serializers.CharField(source="attribute.slug", read_only=True)
    option_value = serializers.CharField(source="option.value", read_only=True)
    option_label = serializers.CharField(source="option.label", read_only=True)
    color_hex = serializers.CharField(source="option.color_hex", read_only=True)

    class Meta:
        model = VariantAttribute
        fields = [
            "id",
            "attribute",
            "attribute_name",
            "attribute_slug",
            "option",
            "option_value",
            "option_label",
            "color_hex",
        ]
        read_only_fields = ["id"]


class ProductMediaSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProductMedia
        fields = [
            "id",
            "url",
            "alt_text",
            "media_type",
            "is_primary",
            "position",
            "variant",
        ]
        read_only_fields = ["id"]


class ProductVariantSerializer(serializers.ModelSerializer):
    attributes = VariantAttributeSerializer(many=True, read_only=True)
    media = ProductMediaSerializer(many=True, read_only=True)
    effective_price = serializers.DecimalField(
        max_digits=12, decimal_places=2, read_only=True
    )
    is_in_stock = serializers.BooleanField(read_only=True)
    is_low_stock = serializers.BooleanField(read_only=True)

    class Meta:
        model = ProductVariant
        fields = [
            "id",
            "sku",
            "barcode",
            "name",
            "price",
            "compare_at_price",
            "cost_price",
            "effective_price",
            "stock_quantity",
            "low_stock_threshold",
            "track_inventory",
            "allow_backorder",
            "weight",
            "is_active",
            "position",
            "is_in_stock",
            "is_low_stock",
            "attributes",
            "media",
            "metadata",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]


class ProductVariantListSerializer(serializers.ModelSerializer):
    effective_price = serializers.DecimalField(
        max_digits=12, decimal_places=2, read_only=True
    )
    is_in_stock = serializers.BooleanField(read_only=True)
    primary_image = serializers.SerializerMethodField()

    class Meta:
        model = ProductVariant
        fields = [
            "id",
            "sku",
            "name",
            "effective_price",
            "stock_quantity",
            "is_active",
            "is_in_stock",
            "primary_image",
        ]

    def get_primary_image(self, obj: ProductVariant) -> str | None:
        if hasattr(obj, "_primary_image"):
            return obj._primary_image
        media = obj.media.filter(is_primary=True).first()
        return media.url if media else None


class ProductAttributeSerializer(serializers.ModelSerializer):
    attribute_name = serializers.CharField(source="attribute.name", read_only=True)
    attribute_slug = serializers.CharField(source="attribute.slug", read_only=True)
    attribute_type = serializers.CharField(source="attribute.attribute_type", read_only=True)
    display_value = serializers.SerializerMethodField()

    class Meta:
        model = ProductAttribute
        fields = [
            "id",
            "attribute",
            "attribute_name",
            "attribute_slug",
            "attribute_type",
            "value_text",
            "value_number",
            "value_boolean",
            "value_option",
            "display_value",
        ]
        read_only_fields = ["id"]

    def get_display_value(self, obj: ProductAttribute) -> Any:
        return obj.get_value()


class ProductSerializer(serializers.ModelSerializer):
    brand_name = serializers.CharField(source="brand.name", read_only=True)
    category_name = serializers.CharField(source="category.name", read_only=True)
    category_path = serializers.CharField(source="category.path", read_only=True)
    attributes = ProductAttributeSerializer(many=True, read_only=True)
    variants = ProductVariantSerializer(many=True, read_only=True)
    media = ProductMediaSerializer(many=True, read_only=True)
    primary_image = serializers.SerializerMethodField()
    variants_count = serializers.SerializerMethodField()

    class Meta:
        model = Product
        fields = [
            "id",
            "name",
            "slug",
            "description",
            "short_description",
            "brand",
            "brand_name",
            "category",
            "category_name",
            "category_path",
            "status",
            "base_price",
            "compare_at_price",
            "cost_price",
            "currency",
            "tax_class",
            "is_taxable",
            "weight",
            "weight_unit",
            "has_variants",
            "seo_title",
            "seo_description",
            "primary_image",
            "variants_count",
            "attributes",
            "variants",
            "media",
            "metadata",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]

    def get_primary_image(self, obj: Product) -> str | None:
        if hasattr(obj, "_primary_image"):
            return obj._primary_image
        media = obj.media.filter(is_primary=True).first()
        return media.url if media else None

    def get_variants_count(self, obj: Product) -> int:
        if hasattr(obj, "_variants_count"):
            return obj._variants_count
        return obj.variants.count()


class ProductListSerializer(serializers.ModelSerializer):
    brand_name = serializers.CharField(source="brand.name", read_only=True)
    category_name = serializers.CharField(source="category.name", read_only=True)
    primary_image = serializers.SerializerMethodField()
    variants_count = serializers.SerializerMethodField()
    min_price = serializers.SerializerMethodField()
    max_price = serializers.SerializerMethodField()
    total_stock = serializers.SerializerMethodField()

    class Meta:
        model = Product
        fields = [
            "id",
            "name",
            "slug",
            "short_description",
            "brand",
            "brand_name",
            "category",
            "category_name",
            "status",
            "base_price",
            "compare_at_price",
            "currency",
            "has_variants",
            "primary_image",
            "variants_count",
            "min_price",
            "max_price",
            "total_stock",
            "created_at",
        ]

    def get_primary_image(self, obj: Product) -> str | None:
        if hasattr(obj, "_primary_image"):
            return obj._primary_image
        media = obj.media.filter(is_primary=True).first()
        return media.url if media else None

    def get_variants_count(self, obj: Product) -> int:
        if hasattr(obj, "_variants_count"):
            return obj._variants_count
        return obj.variants.count()

    def get_min_price(self, obj: Product) -> Decimal:
        if hasattr(obj, "_min_price"):
            return obj._min_price
        prices = [v.effective_price for v in obj.variants.filter(is_active=True)]
        return min(prices) if prices else obj.base_price

    def get_max_price(self, obj: Product) -> Decimal:
        if hasattr(obj, "_max_price"):
            return obj._max_price
        prices = [v.effective_price for v in obj.variants.filter(is_active=True)]
        return max(prices) if prices else obj.base_price

    def get_total_stock(self, obj: Product) -> int:
        if hasattr(obj, "_total_stock"):
            return obj._total_stock
        return sum(v.stock_quantity for v in obj.variants.all())


class OrderLineSerializer(serializers.ModelSerializer):
    class Meta:
        model = OrderLine
        fields = [
            "id",
            "variant",
            "product_name",
            "variant_name",
            "sku",
            "quantity",
            "unit_price",
            "discount_amount",
            "tax_amount",
            "total",
            "metadata",
        ]
        read_only_fields = ["id", "total"]


class OrderSerializer(serializers.ModelSerializer):
    lines = OrderLineSerializer(many=True, read_only=True)
    contact_name = serializers.CharField(source="contact.name", read_only=True)

    class Meta:
        model = Order
        fields = [
            "id",
            "order_number",
            "customer_email",
            "customer_name",
            "customer_phone",
            "contact",
            "contact_name",
            "status",
            "payment_status",
            "subtotal",
            "discount_amount",
            "tax_amount",
            "shipping_amount",
            "total",
            "currency",
            "shipping_address",
            "billing_address",
            "notes",
            "internal_notes",
            "lines",
            "metadata",
            "placed_at",
            "shipped_at",
            "delivered_at",
            "cancelled_at",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "subtotal",
            "total",
            "placed_at",
            "shipped_at",
            "delivered_at",
            "cancelled_at",
            "created_at",
            "updated_at",
        ]


class OrderListSerializer(serializers.ModelSerializer):
    lines_count = serializers.SerializerMethodField()

    class Meta:
        model = Order
        fields = [
            "id",
            "order_number",
            "customer_name",
            "customer_email",
            "status",
            "payment_status",
            "total",
            "currency",
            "lines_count",
            "placed_at",
            "created_at",
        ]

    def get_lines_count(self, obj: Order) -> int:
        if hasattr(obj, "_lines_count"):
            return obj._lines_count
        return obj.lines.count()


class OrderCreateSerializer(serializers.Serializer):
    customer_email = serializers.EmailField()
    customer_name = serializers.CharField(max_length=255)
    customer_phone = serializers.CharField(max_length=50, required=False, default="")
    shipping_address = serializers.JSONField(required=False, default=dict)
    billing_address = serializers.JSONField(required=False, default=dict)
    notes = serializers.CharField(required=False, default="")
    currency = serializers.CharField(max_length=3, default="USD")
    lines = serializers.ListField(child=serializers.DictField(), min_length=1)

    def validate_lines(self, value: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        for i, line in enumerate(value):
            if "variant_id" not in line:
                raise serializers.ValidationError(
                    f"Line {i}: variant_id is required"
                )
            if "quantity" not in line or int(line["quantity"]) < 1:
                raise serializers.ValidationError(
                    f"Line {i}: quantity must be at least 1"
                )
        return value
