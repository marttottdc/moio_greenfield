import uuid
from django.db import models

from crm.models import Customer
from crm.models import Address
from moio_platform import settings
from portal.core.tools import generate_qr_code
from portal.models import Tenant, TenantScopedModel


# Create your models here.
class FamLabel(TenantScopedModel):

    id = models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True)
    company_tag = models.CharField(max_length=30, unique=True, default="")
    qr_code = models.ImageField(upload_to='qr_codes/', blank=True, editable=False)
    mac_address = models.CharField(max_length=17, unique=True, blank=True, null=True)
    tenant = models.ForeignKey(Tenant, on_delete=models.SET_NULL, blank=True, null=True)
    created = models.DateTimeField(auto_now_add=True)
    printed_at = models.DateTimeField(null=True, blank=True)
    printed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL
    )

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)  # First save to generate UUID

        if self.mac_address == "":
            self.mac_address = None  # Convert blank mac_address to None to avoid unique constraint violation

        if not self.qr_code:  # If no QR code image yet

            file = generate_qr_code('asset', str(self.id))
            self.qr_code.save(file.name, file, save=False)
            super().save(update_fields=['qr_code'])


class FamLabelPrintConfiguration(TenantScopedModel):

    name = models.CharField(max_length=30, unique=True, default="")
    print_template_id = models.CharField(max_length=10, default="", blank=True)
    logo = models.ImageField(upload_to='logos/', blank=True, editable=True)
    custom_message = models.CharField(max_length=40, blank=True, null=True, default="")
    show_company_tag = models.BooleanField(default=True)
    show_logo = models.BooleanField(default=False)
    show_custom_message = models.BooleanField(default=False)
    show_mac_address = models.BooleanField(default=False)
    show_creation_date = models.BooleanField(default=False)

    def __str__(self):
        return self.name


class FamAssetType(TenantScopedModel):
    name = models.CharField(max_length=30, unique=True)
    description = models.TextField(blank=True, default="")
    tenant = models.ForeignKey(Tenant, on_delete=models.SET_NULL, blank=True, null=True)

    def __str__(self):
        return self.name


class FamAssetBrand(TenantScopedModel):
    name = models.CharField(max_length=30, unique=True)
    description = models.TextField(blank=True, default="")
    tenant = models.ForeignKey(Tenant, on_delete=models.SET_NULL, blank=True, null=True)

    def __str__(self):
        return self.name


class FamAssetModel(TenantScopedModel):

    brand = models.ForeignKey(FamAssetBrand, on_delete=models.SET_NULL, blank=True, null=True)
    name = models.CharField(max_length=30, unique=True, default="Default")
    description = models.TextField(blank=True, default="")
    tenant = models.ForeignKey(Tenant, on_delete=models.SET_NULL, blank=True, null=True)

    def __str__(self):
        return self.name


class AssetPolicy(TenantScopedModel):
    name = models.CharField(max_length=30, unique=True)
    description = models.CharField(max_length=240, null=True, blank=True)
    min_days = models.IntegerField(default=0)
    max_days = models.IntegerField(default=0)
    read_method = models.CharField(max_length=40, null=True, blank=True)
    enabled = models.BooleanField(default=True)
    distance_tolerance = models.IntegerField(default=0)
    tenant = models.ForeignKey(Tenant, on_delete=models.SET_NULL, blank=True, null=True)

    class Meta:
        db_table = 'asset_policy'
        verbose_name_plural = "Asset Policies"

    def __str__(self):
        return self.name


class AssetRecord(TenantScopedModel):

    serial_number = models.CharField(max_length=255)
    brand = models.CharField(max_length=255)
    model = models.CharField(max_length=255)
    type = models.ForeignKey(FamAssetType, on_delete=models.SET_NULL, blank=True, null=True)
    name = models.CharField(max_length=255)
    purchase_date = models.DateField(null=True)
    created_date = models.DateTimeField(null=True)
    last_update = models.DateTimeField(null=True)
    status = models.CharField(max_length=20)
    last_seen = models.BigIntegerField()
    last_location = models.CharField(max_length=35, null=True)
    last_known_latitude = models.DecimalField(max_digits=9, decimal_places=6)
    last_known_longitude = models.DecimalField(max_digits=9, decimal_places=6)
    comment = models.TextField(null=True)
    owner_company = models.CharField(max_length=255, blank='True')
    asset_image = models.ImageField(upload_to='images/', default='default.jpg')
    active = models.BooleanField(default=True)
    compliant = models.BooleanField(default=False)
    policy = models.ForeignKey(AssetPolicy, on_delete=models.CASCADE, null=True)
    label = models.ForeignKey(FamLabel, related_name="asset", on_delete=models.SET_NULL, null=True)
    tenant = models.ForeignKey(Tenant, on_delete=models.SET_NULL, null=True)

    class Meta:
        db_table = 'asset_record'
        verbose_name_plural = "Asset Records"

    def __str__(self):
        return f'{self.brand}-{self.model}-{self.serial_number}'


class AssetScanDetails(TenantScopedModel):

    rssi = models.IntegerField(default=0, null=True, blank=True)
    latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, )
    scanned_by = models.CharField(max_length=35, null=True)
    received_date = models.DateTimeField(null=True)
    full_body = models.JSONField(null=True)
    url = models.URLField(null=True)
    label_id = models.UUIDField(null=True)
    remote_ip = models.CharField(max_length=255, null=True, blank=True)
    info = models.TextField(null=True,blank=True)


    class Meta:
        db_table = 'asset_scan_details'
        verbose_name_plural = "Asset Scan Details"


class AssetDelegation(TenantScopedModel):

    asset_id = models.ForeignKey(AssetRecord, on_delete=models.CASCADE)
    customer_id = models.ForeignKey(Customer, on_delete=models.CASCADE, null=True, blank=True)
    assigned_location = models.ForeignKey(Address, on_delete=models.CASCADE, null=True, blank=True)
    assigned_on = models.DateTimeField(auto_now=True, null=True)
    unassigned_on = models.DateTimeField(null=True, blank=True)
    comment = models.TextField(null=True)
    status = models.CharField(max_length=20, null=True, editable=False)
    visible = models.BooleanField(default=True)

    class Meta:
        db_table = 'asset_delegation'
        verbose_name_plural = "Asset Delegations"


class AssetTransition(TenantScopedModel):

    enabled = models.BooleanField(default=True)
    trigger = models.CharField(max_length=100, null=True, unique=True)
    source = models.CharField(max_length=100, null=True)
    dest = models.CharField(max_length=100, null=True)
    prepare = models.CharField(max_length=100, null=True, blank=True)
    conditions = models.CharField(max_length=100, null=True, blank=True)

    class Meta:
        db_table = 'asset_transition'
        verbose_name_plural = "Asset Transitions"

    def __str__(self):
        return self.trigger


class LabelPrintFormat(TenantScopedModel):
    name = models.CharField(max_length=120, unique=True)
    layout_key = models.CharField(max_length=64, default="square-center-qr")

    # physical label size
    width_mm  = models.DecimalField(max_digits=6, decimal_places=2, default=60)
    height_mm = models.DecimalField(max_digits=6, decimal_places=2, default=60)
    dpi       = models.PositiveIntegerField(default=300)
    bleed_mm  = models.DecimalField(max_digits=5, decimal_places=2, default=0)

    # page/sheet
    page     = models.CharField(max_length=12, default="A4")          # "A4" or "Letter"
    orient   = models.CharField(max_length=12, default="portrait")     # "portrait" or "landscape"
    cols      = models.PositiveIntegerField(default=3)
    rows      = models.PositiveIntegerField(default=8)
    cell_w_mm = models.DecimalField(max_digits=6, decimal_places=2, default=70)
    cell_h_mm = models.DecimalField(max_digits=6, decimal_places=2, default=37)
    gap_x_mm  = models.DecimalField(max_digits=5, decimal_places=2, default=2)
    gap_y_mm  = models.DecimalField(max_digits=5, decimal_places=2, default=2)
    margin_mm = models.DecimalField(max_digits=5, decimal_places=2, default=5)

    # default texts (used in preview and as fallbacks)
    main_text = models.CharField(max_length=200, default="Control de Activos")
    code_text = models.CharField(max_length=200, default="{{ code }}")
    sample_code = models.CharField(max_length=80, default="SAMPLE-001")  # for preview only
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, default=1)
    mappings = models.JSONField(default=dict, blank=True)

    def __str__(self):
        return self.name


class LabelLayout(TenantScopedModel):

    key = models.SlugField(unique=True)            # e.g. "square-center-qr"
    description = models.CharField(max_length=200, blank=True, default="")
    elements = models.JSONField()                  # the list of elements above
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, default=1)
    logo = models.ImageField(upload_to="label_logos/%Y/%m/%d/", blank=True, null=True)

    def __str__(self):
        return self.key
