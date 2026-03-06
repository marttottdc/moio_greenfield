from django.contrib import admin
from fam.models import AssetScanDetails, AssetRecord, AssetDelegation, AssetPolicy, AssetTransition, FamLabel
# fam/admin.py

from django.db import models
from django.forms import Textarea
from fam.models import LabelPrintFormat, LabelLayout


class AssetScanDetailsAdmin(admin.ModelAdmin):

    list_display = ['label_id','scanned_by', 'received_date','info']


class AssetRecordAdmin(admin.ModelAdmin):
    list_display = ['serial_number','brand', 'name', 'last_seen', 'last_location']


class AssetTransitionAdmin(admin.ModelAdmin):
    list_display = ('enabled', 'trigger', 'source', 'dest',)
    list_filter = ('enabled',)


class FamLabelAdmin(admin.ModelAdmin):
    list_display = ['id', 'company_tag', 'qr_code', 'mac_address']


@admin.register(LabelPrintFormat)
class LabelPrintFormatAdmin(admin.ModelAdmin):
    list_display = ("name", "layout_key", "width_mm", "height_mm", "dpi", "page", "orient", "cols", "rows")
    search_fields = ("name", "layout_key")
    list_filter = ("page", "orient", "dpi")
    fieldsets = (
        ("Identity", {"fields": ("name",)}),
        ("Layout", {"fields": ("layout_key",)}),
        ("Label Size (mm/DPI)", {"fields": ("width_mm", "height_mm", "dpi", "bleed_mm")}),
        ("Page / Sheet", {"fields": ("page", "orient", "cols", "rows", "cell_w_mm", "cell_h_mm", "gap_x_mm", "gap_y_mm", "margin_mm")}),
        ("Texts / Preview", {"fields": ("main_text", "code_text", "sample_code")}),
    )


@admin.register(LabelLayout)
class LabelLayoutAdmin(admin.ModelAdmin):
    list_display = ("key", "description")
    search_fields = ("key", "description")
    formfield_overrides = {
        models.JSONField: {"widget": Textarea(attrs={"rows": 20, "cols": 120})},
    }


admin.site.register(AssetScanDetails, AssetScanDetailsAdmin)
admin.site.register(AssetRecord, AssetRecordAdmin)
admin.site.register(AssetDelegation)
admin.site.register(AssetPolicy)
admin.site.register(AssetTransition, AssetTransitionAdmin)
admin.site.register(FamLabel, FamLabelAdmin)