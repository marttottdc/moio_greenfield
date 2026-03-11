from django.contrib import admin
from crm.models import (
    Contact,
    Company,
    Branch,
    Shipment,
    EcommerceOrder,
    Ticket,
    TicketComment,
    Product,
    ProductVariant,
    Stock,
    Customer,
    Address,
    Tag,
    WebhookPayload,
    WebhookConfig,
    ActivityRecord,
    ActivityType,
    ActivitySuggestion,
    KnowledgeItem,
    ContactType,
    FaceDetection,
    Face,
    ShopifyProduct,
    ShopifyCustomer,
    ShopifyOrder,
    ShopifySyncLog,
)
from central_hub.webhooks.utils import generate_auth_config
from django.utils.html import format_html


# Register your models here.

class ContactTypeAdmin(admin.ModelAdmin):
    list_display = ('id', 'name',)


class ContactAdmin(admin.ModelAdmin):
    list_display = ('pk', 'whatsapp_name', 'phone', 'email', 'fullname', 'created', 'source')
    search_fields = ["phone", "email", "whatsapp_name", "fullname"]
    list_filter = ['tenant', 'source', ]


class BranchAdmin(admin.ModelAdmin):
    list_display = ('name', 'address', 'city', 'type', 'latitude', 'longitude', 'contacto')


class EcommerceOrderAdmin(admin.ModelAdmin):
    list_display = ('order_number', 'created', 'customer_name', 'customer_phone', 'customer_email', 'status')
    list_filter = ['status']
    search_fields = ['order_number', 'customer_name']


class ShipmentAdmin(admin.ModelAdmin):
    list_display = ('order', 'recipient_name', 'comments', 'shipping_notes', 'tracking_code', 'delivery_status', 'closed')


class ProductAdmin(admin.ModelAdmin):
    list_display = ('tenant', 'name', 'description', 'price', 'sale_price', 'brand', 'product_type', 'category')


class ActivityRecordAdmin(admin.ModelAdmin):
    list_display = ("id", "created_at", "title", "status", "user", "source", "kind", "visibility")
    list_filter = ("status", "kind", "source", "tenant")


class ActivityTypeAdmin(admin.ModelAdmin):
    list_display = ("key", "label", "category", "tenant", "order")
    list_filter = ("tenant", "category")


class ActivitySuggestionAdmin(admin.ModelAdmin):
    list_display = ("id", "type_key", "reason", "status", "suggested_at", "tenant")
    list_filter = ("status", "tenant")


class FaceAdmin(admin.ModelAdmin):
    list_display = ('thumbnail', 'id', 'seen', 'last_seen', 'contact')
    search_fields = ['id']

    def thumbnail(self, obj):
        if obj.image and obj.image.url:
            return format_html(
                '<img src="{}" style="height:60px; object-fit:cover;" />',
                obj.image.url,
            )
        return "—"
    thumbnail.short_description = "Image"


class FaceDetectionAdmin(admin.ModelAdmin):
    list_display = ('thumbnail', 'face', 'created', 'distance')

    def thumbnail(self, obj):
        if obj.image and obj.image.url:
            return format_html(
                '<img src="{}" style="height:60px; object-fit:cover;" />',
                obj.image.url,
            )
        return "—"

    thumbnail.short_description = "Image"


class TicketAdmin(admin.ModelAdmin):
    list_display = ('type', 'service', 'created', 'last_updated', 'creator', 'status')
    list_filter = ['type', 'service','status','assigned', 'creator']


@admin.register(WebhookConfig)
class WebhookConfigAdmin(admin.ModelAdmin):
    list_display = ("name", "auth_type", "handler_path", "locked", "linked_flows_count")
    readonly_fields = ("url",)
    filter_horizontal = ("linked_flows",)
    fieldsets = (
        ("General", {"fields": ("name", "description", "locked", "store_payloads")}),
        ("Validation", {"fields": ("expected_content_type",
                                   "expected_origin",
                                   "expected_schema")}),
        ("Authentication", {"fields": ("auth_type", "auth_config")}),
        ("Dispatch", {"fields": ("handler_path",)}),
        ("Flow Integration", {"fields": ("linked_flows",)}),
    )

    def linked_flows_count(self, obj):
        return obj.linked_flows.count()
    linked_flows_count.short_description = "Linked Flows"

    def get_changeform_initial_data(self, request):
        initial = super().get_changeform_initial_data(request)
        atype = request.GET.get("auth_type")  # ?auth_type=bearer in URL
        if atype:
            initial["auth_type"] = atype
            initial["auth_config"] = generate_auth_config(atype)
        return initial


# ===============================================================================
# SHOPIFY INTEGRATION ADMIN
# ===============================================================================

class ShopifyProductAdmin(admin.ModelAdmin):
    list_display = ('shopify_id', 'product', 'handle', 'sync_status', 'last_synced', 'tenant')
    list_filter = ('sync_status', 'tenant', 'last_synced')
    search_fields = ('shopify_id', 'handle', 'product__name')
    readonly_fields = ('shopify_id', 'created_at_shopify', 'updated_at_shopify', 'last_synced')
    raw_id_fields = ('product',)

    def has_add_permission(self, request):
        return False  # Only created via sync

    def has_delete_permission(self, request, obj=None):
        return False  # Prevent manual deletion


class ShopifyCustomerAdmin(admin.ModelAdmin):
    list_display = ('shopify_id', 'customer', 'email', 'first_name', 'last_name', 'last_synced', 'tenant')
    list_filter = ('tenant', 'verified_email', 'accepts_marketing', 'last_synced')
    search_fields = ('shopify_id', 'email', 'first_name', 'last_name', 'customer__name')
    readonly_fields = ('shopify_id', 'created_at_shopify', 'updated_at_shopify', 'last_synced')
    raw_id_fields = ('customer',)

    def has_add_permission(self, request):
        return False  # Only created via sync

    def has_delete_permission(self, request, obj=None):
        return False  # Prevent manual deletion


class ShopifyOrderAdmin(admin.ModelAdmin):
    list_display = ('shopify_id', 'ecommerce_order', 'order_number', 'financial_status', 'fulfillment_status', 'total_price', 'last_synced', 'tenant')
    list_filter = ('financial_status', 'fulfillment_status', 'tenant', 'last_synced')
    search_fields = ('shopify_id', 'order_number', 'email', 'ecommerce_order__order_number')
    readonly_fields = ('shopify_id', 'created_at_shopify', 'updated_at_shopify', 'processed_at', 'last_synced')
    raw_id_fields = ('ecommerce_order',)

    def has_add_permission(self, request):
        return False  # Only created via sync

    def has_delete_permission(self, request, obj=None):
        return False  # Prevent manual deletion


class ShopifySyncLogAdmin(admin.ModelAdmin):
    list_display = ('sync_type', 'status', 'started_at', 'completed_at', 'records_processed', 'records_created', 'records_updated', 'records_failed', 'tenant', 'direction_info')
    list_filter = ('sync_type', 'status', 'tenant', 'started_at')
    search_fields = ('shopify_shop_domain', 'last_shopify_id')
    readonly_fields = ('started_at', 'completed_at', 'error_message', 'error_details')
    ordering = ('-started_at',)

    def has_add_permission(self, request):
        return False  # Only created via sync tasks

    def has_delete_permission(self, request, obj=None):
        # Allow deletion of old completed logs
        return obj and obj.status in ['completed', 'failed'] and obj.completed_at

    def direction_info(self, obj):
        """Display information about data direction."""
        return "Receiving from Shopify"
    direction_info.short_description = "Direction"
    direction_info.admin_order_field = None  # Not sortable

    actions = ['retry_failed_syncs']

    def retry_failed_syncs(self, request, queryset):
        """Retry failed sync operations."""
        from crm.tasks import sync_shopify_products, sync_shopify_customers, sync_shopify_orders

        retry_count = 0
        for sync_log in queryset.filter(status='failed'):
            try:
                if sync_log.sync_type == 'products':
                    sync_shopify_products.delay(sync_log.tenant.id)
                elif sync_log.sync_type == 'customers':
                    sync_shopify_customers.delay(sync_log.tenant.id)
                elif sync_log.sync_type == 'orders':
                    sync_shopify_orders.delay(sync_log.tenant.id)
                retry_count += 1
            except Exception as e:
                self.message_user(request, f"Failed to retry {sync_log}: {e}", level='error')

        self.message_user(request, f"Retried {retry_count} failed syncs.")
    retry_failed_syncs.short_description = "Retry selected failed syncs"


admin.site.register(Contact, ContactAdmin)
admin.site.register(Company)
admin.site.register(Branch, BranchAdmin)
admin.site.register(Shipment, ShipmentAdmin)
admin.site.register(EcommerceOrder, EcommerceOrderAdmin)
admin.site.register(Ticket, TicketAdmin)
admin.site.register(TicketComment)
admin.site.register(Product, ProductAdmin)
admin.site.register(ProductVariant)
admin.site.register(Stock)
admin.site.register(Customer)
admin.site.register(Address)
admin.site.register(Tag)
admin.site.register(WebhookPayload)
admin.site.register(KnowledgeItem)
admin.site.register(ActivityRecord, ActivityRecordAdmin)
admin.site.register(ActivityType, ActivityTypeAdmin)
admin.site.register(ActivitySuggestion, ActivitySuggestionAdmin)
admin.site.register(ContactType, ContactTypeAdmin)
admin.site.register(Face, FaceAdmin)
admin.site.register(FaceDetection, FaceDetectionAdmin)

# Shopify Integration Admin
admin.site.register(ShopifyProduct, ShopifyProductAdmin)
admin.site.register(ShopifyCustomer, ShopifyCustomerAdmin)
admin.site.register(ShopifyOrder, ShopifyOrderAdmin)
admin.site.register(ShopifySyncLog, ShopifySyncLogAdmin)
