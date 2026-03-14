"""Django admin for Agent Console: workspaces, profiles, skills, plugins, automations."""

from django import forms
from django.contrib import admin
from django.core.exceptions import ValidationError

from agent_console.models import (
    AgentConsoleAutomation,
    AgentConsoleInstalledPlugin,
    AgentConsolePluginAssignment,
    AgentConsoleProfile,
    AgentConsoleSession,
    AgentConsoleWorkspace,
    AgentConsoleWorkspaceSkill,
)
from agent_console.services.plugin_installation_service import parse_plugin_bundle_zip


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
    fields = ("plugin_id", "is_enabled", "plugin_config", "notes", "user_allowlist")


class AgentConsoleInstalledPluginAdminForm(forms.ModelForm):
    bundle_upload = forms.FileField(
        required=False,
        help_text="Upload a plugin ZIP bundle containing replica.plugin.json and plugin.py entrypoint.",
    )

    class Meta:
        model = AgentConsoleInstalledPlugin
        fields = ("enabled", "is_platform_approved", "bundle_upload")

    def clean(self):
        cleaned_data = super().clean()
        upload = cleaned_data.get("bundle_upload")
        if upload is None and not self.instance.pk:
            raise ValidationError("Plugin bundle ZIP is required when creating a plugin.")
        if upload is None:
            return cleaned_data
        payload = upload.read()
        try:
            parsed = parse_plugin_bundle_zip(payload)
        except Exception as exc:
            raise ValidationError(f"Invalid plugin bundle: {exc}") from exc
        cleaned_data["_parsed_bundle"] = parsed
        return cleaned_data

    def save(self, commit=True):
        instance = super().save(commit=False)
        parsed = self.cleaned_data.get("_parsed_bundle")
        if parsed is not None:
            instance.plugin_id = parsed.plugin_id
            instance.name = parsed.name
            instance.version = parsed.version
            instance.manifest = parsed.manifest
            instance.checksum_sha256 = parsed.checksum_sha256
            instance.bundle_zip = parsed.bundle_zip
        if commit:
            instance.save()
        return instance


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
    list_display = ("plugin_id", "workspace", "is_enabled")
    list_filter = ("workspace",)
    search_fields = ("plugin_id",)


@admin.register(AgentConsoleInstalledPlugin)
class AgentConsoleInstalledPluginAdmin(admin.ModelAdmin):
    form = AgentConsoleInstalledPluginAdminForm
    list_display = ("plugin_id", "name", "version", "enabled", "is_platform_approved", "updated_at")
    list_filter = ("enabled", "is_platform_approved")
    search_fields = ("plugin_id", "name", "version")
    readonly_fields = ("plugin_id", "name", "version", "checksum_sha256", "created_at", "updated_at")
    fields = (
        "plugin_id",
        "name",
        "version",
        "enabled",
        "is_platform_approved",
        "bundle_upload",
        "checksum_sha256",
        "created_at",
        "updated_at",
    )


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
