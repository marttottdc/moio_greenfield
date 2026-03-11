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

