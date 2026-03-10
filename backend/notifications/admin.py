from django.contrib import admin
from .models import UserNotificationPreference


@admin.register(UserNotificationPreference)
class UserNotificationPreferenceAdmin(admin.ModelAdmin):
    list_display = ("user", "tenant", "channel", "category", "subscribed", "updated_at")
    list_filter = ("channel", "category", "subscribed", "tenant")
    search_fields = ("user__email", "category")
    ordering = ("user", "channel", "category")
