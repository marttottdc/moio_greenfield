from django.contrib import admin

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


class AttributeOptionInline(admin.TabularInline):
    model = AttributeOption
    extra = 1
    fields = ["value", "label", "color_hex", "order"]


class ProductAttributeInline(admin.TabularInline):
    model = ProductAttribute
    extra = 0
    fields = ["attribute", "value_text", "value_number", "value_boolean", "value_option"]
    raw_id_fields = ["attribute", "value_option"]


class VariantAttributeInline(admin.TabularInline):
    model = VariantAttribute
    extra = 0
    fields = ["attribute", "option"]
    raw_id_fields = ["attribute", "option"]


class ProductVariantInline(admin.TabularInline):
    model = ProductVariant
    extra = 0
    fields = ["sku", "name", "price", "stock_quantity", "is_active", "position"]
    readonly_fields = ["sku"]
    show_change_link = True


class ProductMediaInline(admin.TabularInline):
    model = ProductMedia
    extra = 0
    fields = ["url", "alt_text", "media_type", "is_primary", "position"]


class OrderLineInline(admin.TabularInline):
    model = OrderLine
    extra = 0
    readonly_fields = ["product_name", "variant_name", "sku", "quantity", "unit_price", "total"]
    fields = ["product_name", "variant_name", "sku", "quantity", "unit_price", "discount_amount", "tax_amount", "total"]
    can_delete = False


@admin.register(Brand)
class BrandAdmin(admin.ModelAdmin):
    list_display = ["name", "slug", "is_active", "tenant", "created_at"]
    list_filter = ["is_active", "tenant"]
    search_fields = ["name", "slug"]
    prepopulated_fields = {"slug": ("name",)}
    readonly_fields = ["id", "created_at", "updated_at"]


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ["name", "slug", "parent", "depth", "is_active", "tenant"]
    list_filter = ["is_active", "depth", "tenant"]
    search_fields = ["name", "slug", "path"]
    prepopulated_fields = {"slug": ("name",)}
    readonly_fields = ["id", "path", "depth", "created_at", "updated_at"]
    raw_id_fields = ["parent"]


@admin.register(AttributeDefinition)
class AttributeDefinitionAdmin(admin.ModelAdmin):
    list_display = ["name", "slug", "attribute_type", "is_variant_attribute", "is_filterable", "tenant"]
    list_filter = ["attribute_type", "is_variant_attribute", "is_filterable", "tenant"]
    search_fields = ["name", "slug"]
    prepopulated_fields = {"slug": ("name",)}
    readonly_fields = ["id", "created_at", "updated_at"]
    inlines = [AttributeOptionInline]


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ["name", "slug", "status", "base_price", "has_variants", "brand", "category", "tenant"]
    list_filter = ["status", "has_variants", "is_taxable", "tenant"]
    search_fields = ["name", "slug", "description"]
    prepopulated_fields = {"slug": ("name",)}
    readonly_fields = ["id", "created_at", "updated_at"]
    raw_id_fields = ["brand", "category"]
    inlines = [ProductAttributeInline, ProductVariantInline, ProductMediaInline]
    fieldsets = (
        (None, {
            "fields": ("tenant", "name", "slug", "description", "short_description", "status")
        }),
        ("Catalog", {
            "fields": ("brand", "category", "has_variants")
        }),
        ("Pricing", {
            "fields": ("base_price", "compare_at_price", "cost_price", "currency")
        }),
        ("Tax & Shipping", {
            "fields": ("is_taxable", "tax_class", "weight", "weight_unit")
        }),
        ("SEO", {
            "fields": ("seo_title", "seo_description"),
            "classes": ("collapse",)
        }),
        ("Metadata", {
            "fields": ("metadata", "id", "created_at", "updated_at"),
            "classes": ("collapse",)
        }),
    )


@admin.register(ProductVariant)
class ProductVariantAdmin(admin.ModelAdmin):
    list_display = ["sku", "product", "name", "price", "stock_quantity", "is_active", "tenant"]
    list_filter = ["is_active", "track_inventory", "allow_backorder", "tenant"]
    search_fields = ["sku", "barcode", "name", "product__name"]
    readonly_fields = ["id", "created_at", "updated_at"]
    raw_id_fields = ["product"]
    inlines = [VariantAttributeInline]


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ["order_number", "customer_name", "customer_email", "status", "payment_status", "total", "tenant", "created_at"]
    list_filter = ["status", "payment_status", "tenant"]
    search_fields = ["order_number", "customer_name", "customer_email"]
    readonly_fields = ["id", "order_number", "subtotal", "total", "placed_at", "shipped_at", "delivered_at", "cancelled_at", "created_at", "updated_at"]
    raw_id_fields = ["contact"]
    inlines = [OrderLineInline]
    fieldsets = (
        (None, {
            "fields": ("tenant", "order_number", "status", "payment_status")
        }),
        ("Customer", {
            "fields": ("customer_name", "customer_email", "customer_phone", "contact")
        }),
        ("Totals", {
            "fields": ("subtotal", "discount_amount", "tax_amount", "shipping_amount", "total", "currency")
        }),
        ("Addresses", {
            "fields": ("shipping_address", "billing_address"),
            "classes": ("collapse",)
        }),
        ("Notes", {
            "fields": ("notes", "internal_notes"),
            "classes": ("collapse",)
        }),
        ("Timestamps", {
            "fields": ("placed_at", "shipped_at", "delivered_at", "cancelled_at", "created_at", "updated_at"),
            "classes": ("collapse",)
        }),
    )
