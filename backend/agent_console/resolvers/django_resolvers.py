"""
Build resolver callables for AgentConsoleBackend from Django models.
Resolvers run in tenant schema context and return data the runtime expects.
"""
from __future__ import annotations

from typing import Any, Callable

from tenancy.tenant_support import tenant_schema_context

from agent_console.models import (
    AgentConsoleProfile,
    AgentConsolePluginAssignment,
    AgentConsoleWorkspace,
    AgentConsoleWorkspaceSkill,
)


def build_resolvers_for_backend(
    tenant_schema: str,
    workspace_slug: str,
) -> dict[str, Callable[..., Any]]:
    """Build resolver callables that close over tenant_schema and workspace_slug."""

    def workspace_profile_resolver() -> dict[str, Any]:
        with tenant_schema_context(tenant_schema):
            ws = AgentConsoleWorkspace.objects.filter(slug=workspace_slug).first()
            if not ws:
                return {}
            settings_payload = ws.settings if isinstance(ws.settings, dict) else {}
            tool_allowlist = settings_payload.get("toolAllowlist")
            tool_allowlist = (
                [str(item).strip() for item in tool_allowlist if str(item).strip()]
                if isinstance(tool_allowlist, list)
                else []
            )
            return {
                "name": (ws.name or "").strip(),
                "slug": (ws.slug or "").strip(),
                "specialtyPrompt": (ws.specialty_prompt or "").strip(),
                "defaultModel": (ws.default_model or "").strip(),
                "defaultVendor": (ws.default_vendor or "").strip(),
                "defaultThinking": (ws.default_thinking or "").strip(),
                "defaultVerbosity": (ws.default_verbosity or "").strip(),
                "defaultAgentProfileKey": (ws.default_agent_profile_key or "").strip(),
                "toolAllowlist": tool_allowlist,
            }

    def workspace_skills_resolver() -> list[dict[str, Any]]:
        with tenant_schema_context(tenant_schema):
            ws = AgentConsoleWorkspace.objects.filter(slug=workspace_slug).first()
            if not ws:
                return []
            skills = AgentConsoleWorkspaceSkill.objects.filter(workspace=ws, enabled=True).order_by("skill_id")
            return [
                {
                    "key": (s.skill_id or "").strip(),
                    "name": (s.name or s.skill_id or "").strip(),
                    "description": (s.description or "").strip(),
                    "bodyMarkdown": (s.body_markdown or "").strip(),
                }
                for s in skills
            ]

    def agent_profile_state_resolver(
        initiator: dict[str, Any] | None,
        selected_profile: str | None,
    ) -> dict[str, Any]:
        with tenant_schema_context(tenant_schema):
            ws = AgentConsoleWorkspace.objects.filter(slug=workspace_slug).first()
            if ws is not None:
                profiles_qs = AgentConsoleProfile.objects.filter(workspace=ws).order_by("sort_order", "key")
            else:
                profiles_qs = AgentConsoleProfile.objects.filter(workspace__isnull=True).order_by("sort_order", "key")
            profiles = []
            default_key = (ws.default_agent_profile_key if ws else "") or "default"
            active_key = (selected_profile or "").strip() or default_key
            active_profile = {}
            for p in profiles_qs:
                entry = {
                    "key": (p.key or "").strip(),
                    "name": (p.name or p.key or "").strip(),
                    "defaultModel": (p.default_model or "").strip(),
                    "defaultVendor": (p.default_vendor or "").strip(),
                    "defaultThinking": (p.default_thinking or "").strip(),
                    "defaultVerbosity": (p.default_verbosity or "").strip(),
                    "systemPrompt": (p.system_prompt_override or "").strip(),
                    "toolAllowlist": list(p.tool_allowlist) if isinstance(p.tool_allowlist, list) else [],
                }
                profiles.append(entry)
                if (p.key or "").strip() == active_key:
                    active_profile = entry
            if not active_profile and profiles:
                active_profile = profiles[0]
            return {
                "profiles": profiles,
                "activeProfile": active_profile,
                "diagnostics": {
                    "requestedProfile": (selected_profile or "").strip(),
                    "resolvedProfile": active_key,
                    "selectionSource": "django",
                    "requestedProfileRejected": False,
                    "hasExplicitAssignments": True,
                    "initiatorIsAdmin": (initiator or {}).get("tenantAdmin") is True,
                },
            }

    def agent_profiles_catalog_resolver() -> dict[str, Any]:
        with tenant_schema_context(tenant_schema):
            ws = AgentConsoleWorkspace.objects.filter(slug=workspace_slug).first()
            if ws is not None:
                profiles_qs = AgentConsoleProfile.objects.filter(workspace=ws).order_by("sort_order", "key")
            else:
                profiles_qs = AgentConsoleProfile.objects.filter(workspace__isnull=True).order_by("sort_order", "key")
            profiles = [
                {
                    "key": (p.key or "").strip(),
                    "name": (p.name or p.key or "").strip(),
                    "defaultModel": (p.default_model or "").strip(),
                    "defaultVendor": (p.default_vendor or "").strip(),
                    "defaultThinking": (p.default_thinking or "").strip(),
                    "defaultVerbosity": (p.default_verbosity or "").strip(),
                    "systemPrompt": (p.system_prompt_override or "").strip(),
                    "toolAllowlist": list(p.tool_allowlist) if isinstance(p.tool_allowlist, list) else [],
                }
                for p in profiles_qs
            ]
            return {"profiles": profiles, "assignments": []}

    def agent_profile_upsert_handler(
        payload: dict[str, Any],
        initiator: dict[str, Any] | None,
    ) -> dict[str, Any]:
        with tenant_schema_context(tenant_schema):
            ws = AgentConsoleWorkspace.objects.filter(slug=workspace_slug).first()
            key = (payload.get("key") or "").strip() or "default"
            profile, _ = AgentConsoleProfile.objects.update_or_create(
                workspace=ws,
                key=key,
                defaults={
                    "name": (payload.get("name") or key).strip(),
                    "default_model": (payload.get("defaultModel") or "").strip(),
                    "default_vendor": (payload.get("defaultVendor") or "").strip(),
                    "default_thinking": (payload.get("defaultThinking") or "").strip(),
                    "default_verbosity": (payload.get("defaultVerbosity") or "").strip(),
                    "system_prompt_override": (payload.get("systemPrompt") or "").strip(),
                    "tool_allowlist": list(payload.get("toolAllowlist", [])) if isinstance(payload.get("toolAllowlist"), list) else [],
                },
            )
            return {
                "key": (profile.key or "").strip(),
                "name": (profile.name or profile.key or "").strip(),
                "defaultModel": (profile.default_model or "").strip(),
                "defaultVendor": (profile.default_vendor or "").strip(),
                "defaultThinking": (profile.default_thinking or "").strip(),
                "defaultVerbosity": (profile.default_verbosity or "").strip(),
                "systemPrompt": (profile.system_prompt_override or "").strip(),
                "toolAllowlist": list(profile.tool_allowlist) if isinstance(profile.tool_allowlist, list) else [],
            }

    def plugin_user_allowlist_resolver(initiator: dict[str, Any] | None) -> list[str]:
        with tenant_schema_context(tenant_schema):
            ws = AgentConsoleWorkspace.objects.filter(slug=workspace_slug).first()
            if not ws:
                return []
            assignments = AgentConsolePluginAssignment.objects.filter(workspace=ws)
            allowed_plugins = []
            for a in assignments:
                allowlist = list(a.user_allowlist) if isinstance(a.user_allowlist, list) else []
                if not allowlist:
                    allowed_plugins.append((a.plugin_id or "").strip().lower())
                    continue
                user_email = (initiator or {}).get("email") or ""
                user_role = (initiator or {}).get("tenantRole") or "member"
                if "admin" in allowlist and user_role == "admin":
                    allowed_plugins.append((a.plugin_id or "").strip().lower())
                elif "member" in allowlist:
                    allowed_plugins.append((a.plugin_id or "").strip().lower())
                elif user_email and user_email.lower() in [str(x).strip().lower() for x in allowlist if x not in ("admin", "member")]:
                    allowed_plugins.append((a.plugin_id or "").strip().lower())
            return [p for p in allowed_plugins if p]

    def integration_status_resolver() -> dict[str, Any]:
        from tenancy.tenant_support import public_schema_name
        from django_tenants.utils import schema_context
        from tenancy.models import Tenant

        try:
            with schema_context(public_schema_name()):
                tenant = Tenant.objects.filter(schema_name=tenant_schema).first()
                if not tenant:
                    return {"enabledCount": 0, "integrations": []}
                from central_hub.integrations.models import IntegrationConfig

                configs = IntegrationConfig.objects.filter(tenant=tenant)
                integrations = []
                for c in configs:
                    integrations.append({
                        "slug": (c.slug or "").strip(),
                        "instance_id": (c.instance_id or "default").strip(),
                        "name": (c.name or "").strip(),
                        "enabled": c.enabled,
                        "is_configured": c.is_configured(),
                    })
                return {
                    "enabledCount": sum(1 for i in integrations if i.get("enabled") and i.get("is_configured")),
                    "integrations": integrations,
                }
        except Exception:
            return {"enabledCount": 0, "integrations": []}

    def integration_guidance_resolver() -> str:
        from tenancy.tenant_support import public_schema_name
        from django_tenants.utils import schema_context
        from tenancy.models import Tenant

        try:
            with schema_context(public_schema_name()):
                tenant = Tenant.objects.filter(schema_name=tenant_schema).first()
                if not tenant:
                    return ""
                from central_hub.integrations.models import IntegrationConfig

                configs = IntegrationConfig.objects.filter(tenant=tenant, enabled=True)
                parts = []
                for c in configs:
                    if c.is_configured():
                        parts.append(f"- {c.slug} ({c.instance_id}): configured and enabled.")
                return "\n".join(parts) if parts else ""
        except Exception:
            return ""

    return {
        "workspace_profile_resolver": workspace_profile_resolver,
        "workspace_skills_resolver": workspace_skills_resolver,
        "agent_profile_state_resolver": agent_profile_state_resolver,
        "agent_profiles_catalog_resolver": agent_profiles_catalog_resolver,
        "agent_profile_upsert_handler": agent_profile_upsert_handler,
        "plugin_user_allowlist_resolver": plugin_user_allowlist_resolver,
        "integration_status_resolver": integration_status_resolver,
        "integration_guidance_resolver": integration_guidance_resolver,
    }
