from django import forms
from django.contrib import admin
try:
    from django_json_widget.widgets import JSONEditorWidget
except ImportError:  # pragma: no cover - fallback when optional dependency is missing
    from django.forms import widgets as _widgets

    class JSONEditorWidget(_widgets.Textarea):
        pass

from central_hub.models import Capability, Plan, PlatformConfiguration, PlatformNotificationSettings, ProvisioningJob, Role, Tenant
from central_hub.integrations.models import IntegrationConfig
from central_hub.integrations.v1.models import ExternalAccount, EmailAccount, CalendarAccount


class WebhookPayloadAdmin(admin.ModelAdmin):
    list_display = ('pk', 'headers', 'body', 'status', 'creation_date')


class TenantAdminForm(forms.ModelForm):
    features = forms.JSONField(required=False, widget=JSONEditorWidget)
    limits = forms.JSONField(required=False, widget=JSONEditorWidget)
    ui = forms.JSONField(required=False, widget=JSONEditorWidget)

    class Meta:
        model = Tenant
        fields = "__all__"


class TenantAdmin(admin.ModelAdmin):
    form = TenantAdminForm
    list_display = ("nombre", "enabled", "domain", "plan", "tenant_code")
    list_filter = ("plan", "enabled")
    search_fields = ("nombre", "domain", "subdomain")


class IntegrationConfigAdminForm(forms.ModelForm):
    config = forms.JSONField(required=False, widget=JSONEditorWidget)
    metadata = forms.JSONField(required=False, widget=JSONEditorWidget)

    class Meta:
        model = IntegrationConfig
        fields = "__all__"


class IntegrationConfigAdmin(admin.ModelAdmin):
    form = IntegrationConfigAdminForm
    list_display = ("slug", "instance_id", "tenant", "enabled", "name", "created_at", "updated_at")
    list_filter = ("slug", "enabled", "tenant")
    search_fields = ("slug", "instance_id", "name", "tenant__nombre")
    readonly_fields = ("created_at", "updated_at")


class ExternalAccountAdmin(admin.ModelAdmin):
    list_display = ("email_address", "provider", "ownership", "tenant", "owner_user", "is_active")
    list_filter = ("provider", "ownership", "is_active", "tenant")
    search_fields = ("email_address", "tenant__nombre", "owner_user__email")


class EmailAccountAdmin(admin.ModelAdmin):
    list_display = ("id", "external_account", "tenant", "inbox")
    list_filter = ("external_account__provider", "tenant")
    search_fields = ("external_account__email_address",)


class CalendarAccountAdmin(admin.ModelAdmin):
    list_display = ("id", "external_account", "tenant", "calendar_id")
    list_filter = ("external_account__provider", "tenant")
    search_fields = ("external_account__email_address",)


class PlanAdmin(admin.ModelAdmin):
    list_display = ("key", "name", "display_order", "is_active", "is_self_provision_default")
    list_editable = ("name", "display_order", "is_active", "is_self_provision_default")
    ordering = ("display_order", "key")


class CapabilityAdmin(admin.ModelAdmin):
    list_display = ("key", "label")
    search_fields = ("key", "label")


class RoleAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "display_order")
    list_editable = ("display_order",)
    filter_horizontal = ("capabilities",)
    prepopulated_fields = {"slug": ("name",)}


class ProvisioningJobAdmin(admin.ModelAdmin):
    list_display = ("id", "status", "current_stage", "requested_name", "requested_email", "tenant", "user", "created_at")
    list_filter = ("status", "current_stage", "requested_locale", "created_at")
    search_fields = ("requested_name", "requested_email", "requested_subdomain")
    readonly_fields = ("stages", "error_message", "created_at", "updated_at")


admin.site.register(Plan, PlanAdmin)
admin.site.register(Capability, CapabilityAdmin)
admin.site.register(Role, RoleAdmin)
admin.site.register(ProvisioningJob, ProvisioningJobAdmin)
admin.site.register(PlatformConfiguration)
admin.site.register(PlatformNotificationSettings)
admin.site.register(Tenant, TenantAdmin)
admin.site.register(IntegrationConfig, IntegrationConfigAdmin)
admin.site.register(ExternalAccount, ExternalAccountAdmin)
admin.site.register(EmailAccount, EmailAccountAdmin)
admin.site.register(CalendarAccount, CalendarAccountAdmin)