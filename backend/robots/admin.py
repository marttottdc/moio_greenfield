from django.contrib import admin

from .models import Robot, RobotEvent, RobotMemory, RobotRun, RobotSession


@admin.register(Robot)
class RobotAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "tenant", "enabled", "updated_at")
    list_filter = ("enabled", "tenant")
    search_fields = ("name", "slug")
    readonly_fields = ("created_at", "updated_at")


@admin.register(RobotSession)
class RobotSessionAdmin(admin.ModelAdmin):
    list_display = ("id", "robot", "session_key", "run_id", "updated_at")
    list_filter = ("robot",)
    search_fields = ("session_key",)
    readonly_fields = ("created_at", "updated_at")


@admin.register(RobotRun)
class RobotRunAdmin(admin.ModelAdmin):
    list_display = ("id", "robot", "session", "status", "trigger_source", "started_at", "completed_at")
    list_filter = ("status", "trigger_source", "robot")
    search_fields = ("id",)
    readonly_fields = ("started_at", "completed_at")


@admin.register(RobotMemory)
class RobotMemoryAdmin(admin.ModelAdmin):
    list_display = ("id", "robot", "session", "kind", "created_at", "expires_at")
    list_filter = ("kind", "robot")
    readonly_fields = ("created_at",)


@admin.register(RobotEvent)
class RobotEventAdmin(admin.ModelAdmin):
    list_display = ("id", "robot", "run", "event_type", "created_at")
    list_filter = ("event_type", "robot")
    search_fields = ("event_type",)
    readonly_fields = ("created_at",)
