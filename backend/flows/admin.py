from django.contrib import admin
from .models import (
    EventDefinition,
    EventLog,
    Flow,
    FlowExecution,
    FlowGraphVersion,
    FlowInput,
    FlowSchedule,
    FlowScript,
    FlowScriptLog,
    FlowScriptRun,
    FlowScriptVersion,
    FlowVersion,
    FlowVersionStatus,
    FlowWebhook,
)


@admin.register(Flow)
class FlowAdmin(admin.ModelAdmin):
    list_display = ("name", "tenant", "status", "is_enabled", "published_version", "updated_at")
    list_filter = ("status", "tenant")
    search_fields = ("name", "description")
    readonly_fields = ("is_enabled",)


@admin.register(FlowExecution)
class FlowExecutionAdmin(admin.ModelAdmin):
    list_display = ("flow", "status", "started_at", "completed_at")
    list_filter = ("status",)
    search_fields = ("flow__name",)


@admin.register(FlowInput)
class FlowInputAdmin(admin.ModelAdmin):
    list_display = ("flow", "name", "data_type", "is_required")


@admin.register(FlowSchedule)
class FlowScheduleAdmin(admin.ModelAdmin):
    list_display = ("flow", "cron_expression", "timezone", "is_active", "next_run_at")


@admin.register(FlowWebhook)
class FlowWebhookAdmin(admin.ModelAdmin):
    list_display = ("flow", "http_method", "endpoint_path", "last_called_at", "total_calls")


@admin.register(FlowGraphVersion)
class FlowGraphVersionAdmin(admin.ModelAdmin):
    list_display = ("flow", "major", "minor", "is_published", "created_at")
    list_filter = ("is_published",)


@admin.register(FlowVersion)
class FlowVersionAdmin(admin.ModelAdmin):
    list_display = ("flow", "version", "status", "label", "created_at", "updated_at", "published_at")
    list_filter = ("status", "tenant")
    search_fields = ("flow__name", "label", "notes")
    readonly_fields = ("created_at", "updated_at", "published_at", "testing_started_at")
    
    actions = ['start_testing_action', 'back_to_design_action', 'publish_action', 'archive_action']
    
    @admin.action(description="Start Testing (move to testing status)")
    def start_testing_action(self, request, queryset):
        for version in queryset.filter(status=FlowVersionStatus.DRAFT):
            try:
                version.start_testing()
                version.save()
                self.message_user(request, f"Version {version} moved to testing.")
            except Exception as e:
                self.message_user(request, f"Error for {version}: {e}", level='ERROR')
    
    @admin.action(description="Back to Design (move to draft status)")
    def back_to_design_action(self, request, queryset):
        for version in queryset.filter(status=FlowVersionStatus.TESTING):
            try:
                version.back_to_design()
                version.save()
                self.message_user(request, f"Version {version} moved back to draft.")
            except Exception as e:
                self.message_user(request, f"Error for {version}: {e}", level='ERROR')
    
    @admin.action(description="Publish (move to published status)")
    def publish_action(self, request, queryset):
        for version in queryset.filter(status__in=[FlowVersionStatus.DRAFT, FlowVersionStatus.TESTING]):
            try:
                version.publish()
                version.save()
                self.message_user(request, f"Version {version} published.")
            except Exception as e:
                self.message_user(request, f"Error for {version}: {e}", level='ERROR')
    
    @admin.action(description="Archive (move to archived status)")
    def archive_action(self, request, queryset):
        for version in queryset.filter(status=FlowVersionStatus.PUBLISHED):
            try:
                version.archive()
                version.save()
                self.message_user(request, f"Version {version} archived.")
            except Exception as e:
                self.message_user(request, f"Error for {version}: {e}", level='ERROR')


@admin.register(FlowScript)
class FlowScriptAdmin(admin.ModelAdmin):
    list_display = ("name", "flow", "tenant", "slug", "updated_at")
    list_filter = ("tenant", "flow")
    search_fields = ("name", "slug", "description")


@admin.register(FlowScriptVersion)
class FlowScriptVersionAdmin(admin.ModelAdmin):
    list_display = (
        "script",
        "version_number",
        "is_published",
        "created_at",
        "published_at",
    )
    list_filter = ("script", "tenant", "published_at")
    search_fields = ("script__name", "notes")


@admin.register(FlowScriptRun)
class FlowScriptRunAdmin(admin.ModelAdmin):
    list_display = ("script", "version", "status", "started_at", "completed_at")
    list_filter = ("status", "tenant", "flow")
    search_fields = ("script__name",)


@admin.register(FlowScriptLog)
class FlowScriptLogAdmin(admin.ModelAdmin):
    list_display = ("run", "level", "message", "created_at")
    list_filter = ("level", "tenant")
    search_fields = ("message",)


@admin.register(EventDefinition)
class EventDefinitionAdmin(admin.ModelAdmin):
    list_display = ("name", "label", "entity_type", "category", "active", "created_at")
    list_filter = ("active", "category", "entity_type")
    search_fields = ("name", "label", "description")
    readonly_fields = ("created_at", "updated_at")


@admin.register(EventLog)
class EventLogAdmin(admin.ModelAdmin):
    list_display = ("name", "tenant_id", "entity", "source", "routed", "occurred_at", "created_at")
    list_filter = ("name", "routed", "source")
    search_fields = ("name", "source")
    readonly_fields = ("id", "created_at", "occurred_at", "routed_at")
    date_hierarchy = "occurred_at"
