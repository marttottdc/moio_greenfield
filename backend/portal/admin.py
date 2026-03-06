from django import forms
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.core.exceptions import ValidationError

try:
    from django_json_widget.widgets import JSONEditorWidget
except ImportError:  # pragma: no cover - fallback when optional dependency is missing
    from django.forms import widgets as _widgets

    class JSONEditorWidget(_widgets.Textarea):
        pass

from portal.models import (
    AppConfig,
    AppMenu,
    ComponentTemplate,
    ContentBlock,
    Instruction,
    MoioUser,
    PortalConfiguration,
    Tenant,
    TenantConfiguration,
    UserApiKey,
    UserProfile,
)
from portal.integrations.models import IntegrationConfig
from portal.integrations.v1.models import ExternalAccount, EmailAccount, CalendarAccount

from jsonschema import ValidationError as JSONSchemaValidationError
from jsonschema import validate as jsonschema_validate


class ComponentTemplateAdminForm(forms.ModelForm):
    context_schema = forms.JSONField(required=False, widget=JSONEditorWidget)

    class Meta:
        model = ComponentTemplate
        fields = '__all__'


class ComponentTemplateAdmin(admin.ModelAdmin):
    form = ComponentTemplateAdminForm
    list_display = ('name', 'slug', 'template_path', 'tenant', 'updated_at')
    list_filter = ('tenant',)
    search_fields = ('name', 'slug', 'template_path')
    ordering = ('name',)


class ContentBlockAdminForm(forms.ModelForm):
    context = forms.JSONField(required=False, widget=JSONEditorWidget)

    class Meta:
        model = ContentBlock
        fields = '__all__'

    def clean_context(self):
        context = self.cleaned_data.get('context') or {}
        component = self.cleaned_data.get('component')
        schema = getattr(component, 'context_schema', None) if component else None
        if schema:
            try:
                jsonschema_validate(instance=context, schema=schema)
            except JSONSchemaValidationError as exc:  # pragma: no cover - validation branch
                raise ValidationError(exc.message) from exc
        return context


class ContentBlockAdmin(admin.ModelAdmin):
    form = ContentBlockAdminForm
    list_display = ('group', 'component', 'order', 'visibility', 'is_active', 'tenant', 'updated_at')
    list_filter = ('tenant', 'group', 'visibility', 'is_active')
    search_fields = ('group', 'component__name', 'component__slug', 'title')
    ordering = ('order',)

    def get_queryset(self, request):
        queryset = ContentBlock.all_objects.select_related('component', 'tenant')
        return queryset


class MoioUserAdmin(UserAdmin):
    model = MoioUser
    list_display = ['email', 'username', 'first_name', 'last_name', 'is_staff', 'is_active']
    fieldsets = (
        (None, {'fields': ('first_name', 'last_name', 'avatar', 'email', 'username', 'password', 'tenant', 'phone')}),
        ('Permissions', {'fields': ('is_active', 'is_staff', 'is_superuser', 'groups', 'user_permissions')}),
        ('Important dates', {'fields': ('last_login', 'created')}),
    )
    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': ('first_name', 'last_name', 'avatar', 'email', 'username', 'password1', 'password2', 'tenant', 'phone', 'is_active')}
        ),
    )
    search_fields = ('email', 'username')
    ordering = ('email',)
    list_filter = ['tenant']


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


class UserProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "display_name", "title", "locale", "onboarding_state", "updated_at")
    list_filter = ("locale", "onboarding_state")
    search_fields = ("user__email", "display_name", "title")
    readonly_fields = ("updated_at",)
    raw_id_fields = ("user",)


class InstructionAdmin(admin.ModelAdmin):
    list_display = ('key', 'prompt')


class AppMenuAdmin(admin.ModelAdmin):
    list_display = ('app', 'title', 'url', 'enabled', 'target_area')


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


class UserApiKeyAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "tenant", "name", "is_active", "created_at", "last_used_at")
    list_filter = ("is_active", "tenant")
    search_fields = ("user__email", "name")
    readonly_fields = ("key_hash", "created_at", "last_used_at", "expires_at")


admin.site.register(PortalConfiguration)
admin.site.register(Tenant, TenantAdmin)
admin.site.register(MoioUser, MoioUserAdmin)
admin.site.register(UserProfile, UserProfileAdmin)
admin.site.register(TenantConfiguration)
admin.site.register(Instruction, InstructionAdmin)
admin.site.register(AppMenu, AppMenuAdmin)
admin.site.register(AppConfig)
admin.site.register(ComponentTemplate, ComponentTemplateAdmin)
admin.site.register(ContentBlock, ContentBlockAdmin)
admin.site.register(IntegrationConfig, IntegrationConfigAdmin)
admin.site.register(ExternalAccount, ExternalAccountAdmin)
admin.site.register(EmailAccount, EmailAccountAdmin)
admin.site.register(CalendarAccount, CalendarAccountAdmin)
admin.site.register(UserApiKey, UserApiKeyAdmin)