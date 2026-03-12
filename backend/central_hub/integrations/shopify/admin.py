"""
Shopify Integration Admin Interfaces

Django admin interfaces for Shopify integration management.
"""

from django.contrib import admin
from django.utils.html import format_html

from central_hub.integrations.shopify.models import ShopifyProduct, ShopifyCustomer, ShopifyOrder, ShopifySyncLog


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
        """Retry failed sync operations (uses instance_id from shop domain when present)."""
        from central_hub.integrations.shopify.tasks import sync_shopify_products, sync_shopify_customers, sync_shopify_orders

        def _instance_id_from_log(sync_log):
            domain = (getattr(sync_log, "shopify_shop_domain", None) or "").strip()
            if domain and ".myshopify.com" in domain:
                return domain.replace(".myshopify.com", "").strip()
            return "default"

        retry_count = 0
        for sync_log in queryset.filter(status='failed'):
            try:
                instance_id = _instance_id_from_log(sync_log)
                tid = sync_log.tenant.id
                if sync_log.sync_type == 'products':
                    sync_shopify_products.delay(tenant_id=tid, instance_id=instance_id)
                elif sync_log.sync_type == 'customers':
                    sync_shopify_customers.delay(tenant_id=tid, instance_id=instance_id)
                elif sync_log.sync_type == 'orders':
                    sync_shopify_orders.delay(tenant_id=tid, instance_id=instance_id)
                retry_count += 1
            except Exception as e:
                self.message_user(request, f"Failed to retry {sync_log}: {e}", level='error')

        self.message_user(request, f"Retried {retry_count} failed syncs.")
    retry_failed_syncs.short_description = "Retry selected failed syncs"