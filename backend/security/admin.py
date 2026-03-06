from django.contrib import admin, messages
from .models import ServiceToken


@admin.register(ServiceToken)
class ServiceTokenAdmin(admin.ModelAdmin):
    list_display = ("service_name", "tenant_id", "duration_hours", "created_at", "expires_at", "is_active", "short_token")
    list_filter = ("is_active", "created_at", "service_name")
    search_fields = ("service_name", "tenant_id")
    readonly_fields = ("token", "created_at", "expires_at", "id")

    fieldsets = (
        ('Service Info', {
            'fields': ('service_name', 'tenant_id', 'is_active')
        }),
        ('Token Settings', {
            'fields': ('duration_hours',),
            'description': 'How long the token remains valid (in hours).'
        }),
        ('Scopes', {
            'fields': ('scopes',),
            'description': 'JSON list of allowed scopes (e.g., ["pages.read", "tenant.config.read"])'
        }),
        ('Token', {
            'fields': ('token', 'created_at', 'expires_at', 'id'),
        }),
    )

    actions = ["generate_new_token"]

    def short_token(self, obj):
        """Display token preview in list view"""
        if not obj.token:
            return "(no token)"
        return obj.token[:50] + "..."
    short_token.short_description = "Token preview"

    def save_model(self, request, obj, form, change):
        """Auto-generate token when creating"""
        if not obj.token:
            obj.generate_token()
        super().save_model(request, obj, form, change)
        if not change:
            self.message_user(
                request,
                f"Generated token for {obj.service_name}: {obj.token}",
                level=messages.INFO,
            )

    @admin.action(description="Generate new token for selected services")
    def generate_new_token(self, request, queryset):
        """Regenerate tokens for selected services"""
        count = 0
        for obj in queryset:
            obj.generate_token()
            count += 1
        self.message_user(request, f"Regenerated {count} token(s) successfully")
