from django import forms
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

try:
    from django_json_widget.widgets import JSONEditorWidget
except ImportError:
    from django.forms import widgets as _widgets

    class JSONEditorWidget(_widgets.Textarea):
        pass

from tenancy.models import MoioUser, UserApiKey, UserProfile


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


class UserProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "display_name", "title", "locale", "onboarding_state", "updated_at")
    list_filter = ("locale", "onboarding_state")
    search_fields = ("user__email", "display_name", "title")
    readonly_fields = ("updated_at",)
    raw_id_fields = ("user",)


class UserApiKeyAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "tenant", "name", "is_active", "created_at", "last_used_at")
    list_filter = ("is_active", "tenant")
    search_fields = ("user__email", "name")
    readonly_fields = ("key_hash", "created_at", "last_used_at", "expires_at")


admin.site.register(MoioUser, MoioUserAdmin)
admin.site.register(UserProfile, UserProfileAdmin)
admin.site.register(UserApiKey, UserApiKeyAdmin)
