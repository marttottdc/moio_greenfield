"""
Shopify sync models (tenant-scoped).

These models live in the crm app so their migrations run on tenant schemas only,
where crm_product, crm_customer, crm_ecommerceorder exist.
Re-exported from central_hub.integrations.shopify.models for backward compatibility.
"""

from django.db import models
from django.utils import timezone

from tenancy.models import TenantScopedModel


class ShopifyProduct(TenantScopedModel):
    """
    Shopify product sync data.
    Links to local Product model and tracks Shopify-specific data.
    """
    shopify_id = models.CharField(max_length=20, unique=True, db_index=True)
    product = models.OneToOneField(
        "crm.Product",
        on_delete=models.CASCADE,
        related_name='shopify_data',
        null=True,
        blank=True
    )

    handle = models.CharField(max_length=255, blank=True)
    product_type = models.CharField(max_length=255, blank=True)
    vendor = models.CharField(max_length=255, blank=True)
    tags = models.JSONField(default=list, blank=True)
    published_at = models.DateTimeField(null=True, blank=True)
    created_at_shopify = models.DateTimeField(null=True, blank=True)
    updated_at_shopify = models.DateTimeField(null=True, blank=True)
    last_synced = models.DateTimeField(null=True, blank=True)
    sync_status = models.CharField(
        max_length=20,
        choices=[
            ('active', 'Active'),
            ('archived', 'Archived'),
            ('draft', 'Draft'),
        ],
        default='active'
    )

    class Meta:
        db_table = 'shopify_product'
        indexes = [
            models.Index(fields=['tenant', 'shopify_id']),
            models.Index(fields=['last_synced']),
        ]

    def __str__(self):
        return f"Shopify Product {self.shopify_id}"


class ShopifyCustomer(TenantScopedModel):
    """
    Shopify customer sync data.
    Links to local Customer model and tracks Shopify-specific data.
    """
    shopify_id = models.CharField(max_length=20, unique=True, db_index=True)
    customer = models.OneToOneField(
        "crm.Customer",
        on_delete=models.CASCADE,
        related_name='shopify_data',
        null=True,
        blank=True
    )

    email = models.EmailField(blank=True)
    first_name = models.CharField(max_length=255, blank=True)
    last_name = models.CharField(max_length=255, blank=True)
    phone = models.CharField(max_length=50, blank=True)
    verified_email = models.BooleanField(default=False)
    accepts_marketing = models.BooleanField(default=False)
    tax_exempt = models.BooleanField(default=False)
    tags = models.JSONField(default=list, blank=True)
    addresses = models.JSONField(default=list, blank=True)
    default_address = models.JSONField(null=True, blank=True)
    created_at_shopify = models.DateTimeField(null=True, blank=True)
    updated_at_shopify = models.DateTimeField(null=True, blank=True)
    last_synced = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'shopify_customer'
        indexes = [
            models.Index(fields=['tenant', 'shopify_id']),
            models.Index(fields=['email']),
            models.Index(fields=['last_synced']),
        ]

    def __str__(self):
        return f"Shopify Customer {self.shopify_id}"


class ShopifyOrder(TenantScopedModel):
    """
    Shopify order sync data.
    Links to local EcommerceOrder model and tracks Shopify-specific data.
    """
    shopify_id = models.CharField(max_length=20, unique=True, db_index=True)
    ecommerce_order = models.OneToOneField(
        "crm.EcommerceOrder",
        on_delete=models.CASCADE,
        related_name='shopify_data',
        null=True,
        blank=True
    )

    order_number = models.CharField(max_length=20, blank=True)
    name = models.CharField(max_length=50, blank=True)
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=50, blank=True)
    subtotal_price = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    total_tax = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    total_discounts = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    total_price = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    shipping_address = models.JSONField(null=True, blank=True)
    billing_address = models.JSONField(null=True, blank=True)
    shipping_lines = models.JSONField(default=list, blank=True)
    line_items = models.JSONField(default=list, blank=True)
    financial_status = models.CharField(
        max_length=20,
        choices=[
            ('pending', 'Pending'),
            ('authorized', 'Authorized'),
            ('paid', 'Paid'),
            ('partially_paid', 'Partially Paid'),
            ('refunded', 'Refunded'),
            ('voided', 'Voided'),
        ],
        blank=True
    )
    fulfillment_status = models.CharField(
        max_length=20,
        choices=[
            ('fulfilled', 'Fulfilled'),
            ('partial', 'Partial'),
            ('unfulfilled', 'Unfulfilled'),
        ],
        blank=True
    )
    created_at_shopify = models.DateTimeField(null=True, blank=True)
    updated_at_shopify = models.DateTimeField(null=True, blank=True)
    processed_at = models.DateTimeField(null=True, blank=True)
    last_synced = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'shopify_order'
        indexes = [
            models.Index(fields=['tenant', 'shopify_id']),
            models.Index(fields=['order_number']),
            models.Index(fields=['last_synced']),
        ]

    def __str__(self):
        return f"Shopify Order {self.shopify_id}"


class ShopifySyncLog(TenantScopedModel):
    """
    Logs Shopify synchronization activities for debugging and monitoring.
    """
    SYNC_TYPES = [
        ('products', 'Products'),
        ('customers', 'Customers'),
        ('orders', 'Orders'),
    ]

    sync_type = models.CharField(max_length=20, choices=SYNC_TYPES)
    started_at = models.DateTimeField(default=timezone.now)
    completed_at = models.DateTimeField(null=True, blank=True)
    records_processed = models.IntegerField(default=0)
    records_created = models.IntegerField(default=0)
    records_updated = models.IntegerField(default=0)
    records_failed = models.IntegerField(default=0)
    status = models.CharField(
        max_length=20,
        choices=[
            ('running', 'Running'),
            ('completed', 'Completed'),
            ('failed', 'Failed'),
            ('partial', 'Partial Success'),
        ],
        default='running'
    )
    error_message = models.TextField(blank=True)
    error_details = models.JSONField(default=dict, blank=True)
    shopify_shop_domain = models.CharField(max_length=255, blank=True)
    last_shopify_id = models.CharField(max_length=20, blank=True)

    class Meta:
        db_table = 'shopify_sync_log'
        ordering = ['-started_at']
        indexes = [
            models.Index(fields=['tenant', 'sync_type', 'started_at']),
            models.Index(fields=['status']),
        ]

    def __str__(self):
        return f"{self.sync_type} sync - {self.status} - {self.started_at}"

    def mark_completed(self, records_processed=0, records_created=0, records_updated=0, records_failed=0):
        self.completed_at = timezone.now()
        self.records_processed = records_processed
        self.records_created = records_created
        self.records_updated = records_updated
        self.records_failed = records_failed
        self.status = 'completed'
        self.save()

    def mark_failed(self, error_message, error_details=None):
        self.completed_at = timezone.now()
        self.status = 'failed'
        self.error_message = error_message
        if error_details:
            self.error_details = error_details
        self.save()
