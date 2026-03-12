"""Django admin for Agent Console: workspaces, profiles, skills, plugins, automations."""

from django.contrib import admin

from agent_console.models import (
    AgentConsoleAutomation,
    AgentConsolePluginAssignment,
    AgentConsoleProfile,
    AgentConsoleSession,
    AgentConsoleWorkspace,
    AgentConsoleWorkspaceSkill,
)


@admin.register(AgentConsoleWorkspace)
class AgentConsoleWorkspaceAdmin(admin.ModelAdmin):
    list_display = ("slug", "name", "default_agent_profile_key", "default_model")
    list_filter = ()
    search_fields = ("slug", "name")
    prepopulated_fields = {"slug": ("name",)}
    inlines = [
        AgentConsoleProfileInline,
        AgentConsoleWorkspaceSkillInline,
        AgentConsolePluginAssignmentInline,
    ]


class AgentConsoleWorkspaceSkillInline(admin.TabularInline):
    model = AgentConsoleWorkspaceSkill
    extra = 0
    fields = ("skill_id", "name", "description", "body_markdown", "enabled")


class AgentConsoleProfileInline(admin.TabularInline):
    model = AgentConsoleProfile
    extra = 0
    fk_name = "workspace"
    fields = ("key", "name", "default_model", "default_vendor", "default_thinking", "default_verbosity", "sort_order")


class AgentConsolePluginAssignmentInline(admin.TabularInline):
    model = AgentConsolePluginAssignment
    extra = 0
    fields = ("plugin_id", "user_allowlist")


@admin.register(AgentConsoleProfile)
class AgentConsoleProfileAdmin(admin.ModelAdmin):
    list_display = ("key", "name", "workspace", "default_model", "default_vendor", "sort_order")
    list_filter = ("workspace",)
    search_fields = ("key", "name")
    list_editable = ("sort_order",)


@admin.register(AgentConsoleWorkspaceSkill)
class AgentConsoleWorkspaceSkillAdmin(admin.ModelAdmin):
    list_display = ("skill_id", "workspace", "name", "enabled")
    list_filter = ("workspace", "enabled")
    search_fields = ("skill_id", "name")


@admin.register(AgentConsolePluginAssignment)
class AgentConsolePluginAssignmentAdmin(admin.ModelAdmin):
    list_display = ("plugin_id", "workspace")
    list_filter = ("workspace",)
    search_fields = ("plugin_id",)


@admin.register(AgentConsoleSession)
class AgentConsoleSessionAdmin(admin.ModelAdmin):
    list_display = ("session_key", "workspace_slug", "title", "scope", "updated_at")
    list_filter = ("workspace_slug", "scope")
    search_fields = ("session_key", "title")
    readonly_fields = ("workspace_slug", "session_key", "title", "scope", "owner", "payload", "updated_at")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(AgentConsoleAutomation)
class AgentConsoleAutomationAdmin(admin.ModelAdmin):
    list_display = ("name", "workspace_slug", "trigger_type", "session_key", "active", "updated_at")
    list_filter = ("trigger_type", "active")
    search_fields = ("name", "message", "workspace_slug")
    list_editable = ("active",)
    readonly_fields = ("created_at", "updated_at")

    def get_readonly_fields(self, request, obj=None):
        return list(super().get_readonly_fields(request, obj)) + ["created_at", "updated_at"]
