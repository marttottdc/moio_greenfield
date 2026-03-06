from __future__ import annotations

import uuid
from decimal import Decimal
from typing import TYPE_CHECKING, Optional

from django.db import models, transaction
from django.utils.text import slugify

from portal.models import Tenant, TenantManager

if TYPE_CHECKING:
    from django.db.models import QuerySet


class FluidCommerceBaseModel(models.Model):
    """Base model for FluidCommerce with tenant isolation."""
    tenant = models.ForeignKey(
        Tenant,
        on_delete=models.CASCADE,
        related_name="%(app_label)s_%(class)s_set",
    )
    objects = TenantManager()

    class Meta:
        abstract = True


class Brand(FluidCommerceBaseModel):
    """Product brand with optional metadata."""
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=255)
    slug = models.SlugField(max_length=255, db_index=True)
    description = models.TextField(blank=True, default="")
    logo_url = models.URLField(max_length=500, blank=True, default="")
    website_url = models.URLField(max_length=500, blank=True, default="")
    is_active = models.BooleanField(default=True, db_index=True)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = "fluidcommerce"
        db_table = "fluidcommerce_brand"
        unique_together = [("tenant", "slug")]
        ordering = ["name"]
        indexes = [
            models.Index(fields=["tenant", "is_active"]),
        ]

    def __str__(self) -> str:
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)


class Category(FluidCommerceBaseModel):
    """Hierarchical product category with materialized path for efficient tree queries."""
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=255)
    slug = models.SlugField(max_length=255, db_index=True)
    description = models.TextField(blank=True, default="")
    parent = models.ForeignKey(
        "self",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="children",
    )
    image_url = models.URLField(max_length=500, blank=True, default="")
    order = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True, db_index=True)
    path = models.CharField(max_length=1000, blank=True, default="", db_index=True)
    depth = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = "fluidcommerce"
        db_table = "fluidcommerce_category"
        unique_together = [("tenant", "slug")]
        ordering = ["path", "order", "name"]
        verbose_name_plural = "categories"
        indexes = [
            models.Index(fields=["tenant", "is_active"]),
            models.Index(fields=["tenant", "parent"]),
        ]

    def __str__(self) -> str:
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        
        old_path = None
        if self.pk:
            try:
                old_instance = Category.objects.get(pk=self.pk)
                old_path = old_instance.path
            except Category.DoesNotExist:
                pass
        
        self._update_path_and_depth()
        super().save(*args, **kwargs)
        
        if old_path and old_path != self.path:
            self._update_descendants_paths(old_path)

    def _update_path_and_depth(self) -> None:
        if self.parent:
            self.path = f"{self.parent.path}/{self.slug}" if self.parent.path else self.slug
            self.depth = self.parent.depth + 1
        else:
            self.path = self.slug
            self.depth = 0

    def _update_descendants_paths(self, old_path: str) -> None:
        descendants = Category.objects.filter(
            tenant=self.tenant,
            path__startswith=f"{old_path}/",
        )
        for descendant in descendants:
            new_descendant_path = self.path + descendant.path[len(old_path):]
            new_depth = new_descendant_path.count("/")
            Category.objects.filter(pk=descendant.pk).update(
                path=new_descendant_path,
                depth=new_depth,
            )

    def get_ancestors(self) -> "QuerySet[Category]":
        if not self.path:
            return Category.objects.none()
        slugs = self.path.split("/")[:-1]
        return Category.objects.filter(tenant=self.tenant, slug__in=slugs).order_by("depth")

    def get_descendants(self) -> "QuerySet[Category]":
        return Category.objects.filter(
            tenant=self.tenant,
            path__startswith=f"{self.path}/",
        ).order_by("path")


class AttributeDefinition(FluidCommerceBaseModel):
    """Definition of a product attribute (e.g., Color, Size, Material)."""
    
    class AttributeType(models.TextChoices):
        TEXT = "text", "Text"
        NUMBER = "number", "Number"
        BOOLEAN = "boolean", "Boolean"
        SELECT = "select", "Select"
        MULTISELECT = "multiselect", "Multi-Select"
        COLOR = "color", "Color"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=255)
    slug = models.SlugField(max_length=255, db_index=True)
    attribute_type = models.CharField(
        max_length=20,
        choices=AttributeType.choices,
        default=AttributeType.TEXT,
    )
    is_variant_attribute = models.BooleanField(
        default=False,
        help_text="If True, this attribute defines product variants (e.g., Size, Color).",
    )
    is_filterable = models.BooleanField(
        default=False,
        help_text="If True, customers can filter products by this attribute.",
    )
    is_required = models.BooleanField(default=False)
    order = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = "fluidcommerce"
        db_table = "fluidcommerce_attribute_definition"
        unique_together = [("tenant", "slug")]
        ordering = ["order", "name"]
        indexes = [
            models.Index(fields=["tenant", "is_variant_attribute"]),
            models.Index(fields=["tenant", "is_filterable"]),
        ]

    def __str__(self) -> str:
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)


class AttributeOption(models.Model):
    """Predefined option for select/multiselect/color attributes."""
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    attribute = models.ForeignKey(
        AttributeDefinition,
        on_delete=models.CASCADE,
        related_name="options",
    )
    value = models.CharField(max_length=255)
    label = models.CharField(max_length=255, blank=True, default="")
    color_hex = models.CharField(
        max_length=7,
        blank=True,
        default="",
        help_text="Hex color code for color attributes (e.g., #FF0000).",
    )
    order = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = "fluidcommerce"
        db_table = "fluidcommerce_attribute_option"
        unique_together = [("attribute", "value")]
        ordering = ["order", "value"]
        indexes = [
            models.Index(fields=["attribute", "order"]),
        ]

    def __str__(self) -> str:
        return self.label or self.value

    def save(self, *args, **kwargs):
        if not self.label:
            self.label = self.value
        super().save(*args, **kwargs)


class Product(FluidCommerceBaseModel):
    """Product (SPU - Standard Product Unit) representing a product family."""
    
    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        ACTIVE = "active", "Active"
        ARCHIVED = "archived", "Archived"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=500)
    slug = models.SlugField(max_length=500, db_index=True)
    description = models.TextField(blank=True, default="")
    short_description = models.CharField(max_length=500, blank=True, default="")
    brand = models.ForeignKey(
        Brand,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="products",
    )
    category = models.ForeignKey(
        Category,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="products",
    )
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.DRAFT,
        db_index=True,
    )
    base_price = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00"),
    )
    compare_at_price = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Original price for showing discounts.",
    )
    cost_price = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Cost of goods for profit calculations.",
    )
    currency = models.CharField(max_length=3, default="USD")
    tax_class = models.CharField(max_length=100, blank=True, default="")
    is_taxable = models.BooleanField(default=True)
    weight = models.DecimalField(
        max_digits=10,
        decimal_places=3,
        null=True,
        blank=True,
    )
    weight_unit = models.CharField(max_length=10, default="kg")
    has_variants = models.BooleanField(
        default=False,
        help_text="If True, product has multiple variants (SKUs).",
    )
    seo_title = models.CharField(max_length=255, blank=True, default="")
    seo_description = models.TextField(blank=True, default="")
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = "fluidcommerce"
        db_table = "fluidcommerce_product"
        unique_together = [("tenant", "slug")]
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["tenant", "status"]),
            models.Index(fields=["tenant", "category"]),
            models.Index(fields=["tenant", "brand"]),
            models.Index(fields=["tenant", "created_at"]),
        ]

    def __str__(self) -> str:
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)


class ProductAttribute(models.Model):
    """Product-level attribute value (not variant-defining)."""
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        related_name="attributes",
    )
    attribute = models.ForeignKey(
        AttributeDefinition,
        on_delete=models.CASCADE,
        related_name="product_values",
    )
    value_text = models.TextField(blank=True, default="")
    value_number = models.DecimalField(
        max_digits=12,
        decimal_places=4,
        null=True,
        blank=True,
    )
    value_boolean = models.BooleanField(null=True, blank=True)
    value_option = models.ForeignKey(
        AttributeOption,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="product_values",
    )
    value_options = models.ManyToManyField(
        AttributeOption,
        blank=True,
        related_name="product_multiselect_values",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = "fluidcommerce"
        db_table = "fluidcommerce_product_attribute"
        unique_together = [("product", "attribute")]
        indexes = [
            models.Index(fields=["product", "attribute"]),
        ]

    def __str__(self) -> str:
        return f"{self.product.name} - {self.attribute.name}"

    def get_value(self):
        attr_type = self.attribute.attribute_type
        if attr_type == AttributeDefinition.AttributeType.TEXT:
            return self.value_text
        elif attr_type == AttributeDefinition.AttributeType.NUMBER:
            return self.value_number
        elif attr_type == AttributeDefinition.AttributeType.BOOLEAN:
            return self.value_boolean
        elif attr_type == AttributeDefinition.AttributeType.SELECT:
            return self.value_option
        elif attr_type == AttributeDefinition.AttributeType.MULTISELECT:
            return list(self.value_options.all())
        elif attr_type == AttributeDefinition.AttributeType.COLOR:
            return self.value_option
        return None


class ProductVariant(FluidCommerceBaseModel):
    """Product variant (SKU - Stock Keeping Unit) with inventory tracking."""
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        related_name="variants",
    )
    sku = models.CharField(max_length=100, db_index=True)
    barcode = models.CharField(max_length=100, blank=True, default="")
    name = models.CharField(
        max_length=500,
        blank=True,
        default="",
        help_text="Variant name (e.g., 'Red / Large'). Auto-generated if empty.",
    )
    price = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Override price. Falls back to product base_price if null.",
    )
    compare_at_price = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
    )
    cost_price = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
    )
    stock_quantity = models.IntegerField(default=0)
    low_stock_threshold = models.PositiveIntegerField(default=5)
    track_inventory = models.BooleanField(default=True)
    allow_backorder = models.BooleanField(default=False)
    weight = models.DecimalField(
        max_digits=10,
        decimal_places=3,
        null=True,
        blank=True,
    )
    is_active = models.BooleanField(default=True, db_index=True)
    position = models.PositiveIntegerField(default=0)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = "fluidcommerce"
        db_table = "fluidcommerce_product_variant"
        unique_together = [("tenant", "sku")]
        ordering = ["position", "created_at"]
        indexes = [
            models.Index(fields=["tenant", "product"]),
            models.Index(fields=["tenant", "is_active"]),
            models.Index(fields=["product", "position"]),
        ]

    def __str__(self) -> str:
        return f"{self.product.name} - {self.name or self.sku}"

    @property
    def effective_price(self) -> Decimal:
        return self.price if self.price is not None else self.product.base_price

    @property
    def is_in_stock(self) -> bool:
        if not self.track_inventory:
            return True
        return self.stock_quantity > 0 or self.allow_backorder

    @property
    def is_low_stock(self) -> bool:
        if not self.track_inventory:
            return False
        return 0 < self.stock_quantity <= self.low_stock_threshold

    def adjust_stock(self, quantity: int, reason: str = "") -> int:
        self.stock_quantity += quantity
        self.save(update_fields=["stock_quantity", "updated_at"])
        return self.stock_quantity

    def reserve_stock(self, quantity: int) -> bool:
        with transaction.atomic():
            variant = ProductVariant.objects.select_for_update().get(pk=self.pk)
            if not variant.track_inventory:
                return True
            if variant.stock_quantity >= quantity or variant.allow_backorder:
                variant.stock_quantity -= quantity
                variant.save(update_fields=["stock_quantity", "updated_at"])
                return True
            return False


class VariantAttribute(models.Model):
    """Variant-defining attribute value (links variant to attribute option)."""
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    variant = models.ForeignKey(
        ProductVariant,
        on_delete=models.CASCADE,
        related_name="attributes",
    )
    attribute = models.ForeignKey(
        AttributeDefinition,
        on_delete=models.CASCADE,
        related_name="variant_values",
    )
    option = models.ForeignKey(
        AttributeOption,
        on_delete=models.CASCADE,
        related_name="variant_values",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        app_label = "fluidcommerce"
        db_table = "fluidcommerce_variant_attribute"
        unique_together = [("variant", "attribute")]
        indexes = [
            models.Index(fields=["variant", "attribute"]),
            models.Index(fields=["option"]),
        ]

    def __str__(self) -> str:
        return f"{self.variant} - {self.attribute.name}: {self.option}"


class ProductMedia(FluidCommerceBaseModel):
    """Media files (images, videos) for products and variants."""
    
    class MediaType(models.TextChoices):
        IMAGE = "image", "Image"
        VIDEO = "video", "Video"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        related_name="media",
    )
    variant = models.ForeignKey(
        ProductVariant,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="media",
    )
    url = models.URLField(max_length=1000)
    alt_text = models.CharField(max_length=500, blank=True, default="")
    media_type = models.CharField(
        max_length=10,
        choices=MediaType.choices,
        default=MediaType.IMAGE,
    )
    is_primary = models.BooleanField(default=False)
    position = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = "fluidcommerce"
        db_table = "fluidcommerce_product_media"
        ordering = ["position", "created_at"]
        verbose_name_plural = "product media"
        indexes = [
            models.Index(fields=["product", "position"]),
            models.Index(fields=["product", "is_primary"]),
            models.Index(fields=["variant", "position"]),
        ]

    def __str__(self) -> str:
        return f"{self.product.name} - {self.media_type} #{self.position}"


class Order(FluidCommerceBaseModel):
    """Customer order with shipping and billing information."""
    
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        CONFIRMED = "confirmed", "Confirmed"
        PROCESSING = "processing", "Processing"
        SHIPPED = "shipped", "Shipped"
        DELIVERED = "delivered", "Delivered"
        CANCELLED = "cancelled", "Cancelled"
        REFUNDED = "refunded", "Refunded"

    class PaymentStatus(models.TextChoices):
        PENDING = "pending", "Pending"
        PAID = "paid", "Paid"
        PARTIALLY_PAID = "partially_paid", "Partially Paid"
        REFUNDED = "refunded", "Refunded"
        FAILED = "failed", "Failed"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    order_number = models.CharField(max_length=50, db_index=True)
    customer_email = models.EmailField()
    customer_name = models.CharField(max_length=255)
    customer_phone = models.CharField(max_length=50, blank=True, default="")
    contact = models.ForeignKey(
        "crm.Contact",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="fluidcommerce_orders",
    )
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
        db_index=True,
    )
    payment_status = models.CharField(
        max_length=20,
        choices=PaymentStatus.choices,
        default=PaymentStatus.PENDING,
        db_index=True,
    )
    subtotal = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    discount_amount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    tax_amount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    shipping_amount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    total = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    currency = models.CharField(max_length=3, default="USD")
    shipping_address = models.JSONField(default=dict, blank=True)
    billing_address = models.JSONField(default=dict, blank=True)
    notes = models.TextField(blank=True, default="")
    internal_notes = models.TextField(blank=True, default="")
    metadata = models.JSONField(default=dict, blank=True)
    placed_at = models.DateTimeField(null=True, blank=True)
    shipped_at = models.DateTimeField(null=True, blank=True)
    delivered_at = models.DateTimeField(null=True, blank=True)
    cancelled_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = "fluidcommerce"
        db_table = "fluidcommerce_order"
        unique_together = [("tenant", "order_number")]
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["tenant", "status"]),
            models.Index(fields=["tenant", "payment_status"]),
            models.Index(fields=["tenant", "customer_email"]),
            models.Index(fields=["tenant", "created_at"]),
            models.Index(fields=["tenant", "placed_at"]),
        ]

    def __str__(self) -> str:
        return f"Order {self.order_number}"

    def calculate_totals(self) -> None:
        lines = self.lines.all()
        self.subtotal = sum(line.total for line in lines)
        self.total = self.subtotal - self.discount_amount + self.tax_amount + self.shipping_amount
        self.save(update_fields=["subtotal", "total", "updated_at"])

    def confirm(self) -> None:
        from django.utils import timezone
        self.status = self.Status.CONFIRMED
        self.placed_at = timezone.now()
        self.save(update_fields=["status", "placed_at", "updated_at"])

    def ship(self) -> None:
        from django.utils import timezone
        self.status = self.Status.SHIPPED
        self.shipped_at = timezone.now()
        self.save(update_fields=["status", "shipped_at", "updated_at"])

    def deliver(self) -> None:
        from django.utils import timezone
        self.status = self.Status.DELIVERED
        self.delivered_at = timezone.now()
        self.save(update_fields=["status", "delivered_at", "updated_at"])

    def cancel(self, reason: str = "") -> None:
        from django.utils import timezone
        self.status = self.Status.CANCELLED
        self.cancelled_at = timezone.now()
        if reason:
            self.internal_notes = f"{self.internal_notes}\nCancelled: {reason}".strip()
        self.save(update_fields=["status", "cancelled_at", "internal_notes", "updated_at"])


class OrderLine(models.Model):
    """Individual line item in an order with snapshot data."""
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    order = models.ForeignKey(
        Order,
        on_delete=models.CASCADE,
        related_name="lines",
    )
    variant = models.ForeignKey(
        ProductVariant,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="order_lines",
    )
    product_name = models.CharField(max_length=500)
    variant_name = models.CharField(max_length=500, blank=True, default="")
    sku = models.CharField(max_length=100)
    quantity = models.PositiveIntegerField(default=1)
    unit_price = models.DecimalField(max_digits=12, decimal_places=2)
    discount_amount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    tax_amount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    total = models.DecimalField(max_digits=12, decimal_places=2)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = "fluidcommerce"
        db_table = "fluidcommerce_order_line"
        ordering = ["created_at"]
        indexes = [
            models.Index(fields=["order"]),
            models.Index(fields=["variant"]),
        ]

    def __str__(self) -> str:
        return f"{self.product_name} x{self.quantity}"

    def save(self, *args, **kwargs):
        self.total = (self.unit_price * self.quantity) - self.discount_amount + self.tax_amount
        super().save(*args, **kwargs)
