"""
Tenant Admin API: GET bootstrap, POST users, POST users/delete.

Workspaces, skills, automations, integrations, plugins are handled by the
agent console runtime (moio_runtime / config), not by this API.
"""
from __future__ import annotations

from django.contrib.auth import get_user_model
from django.db.utils import OperationalError, ProgrammingError
import os
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.authentication import JWTAuthentication

from moio_platform.authentication import BearerTokenAuthentication
from central_hub.authentication import CsrfExemptSessionAuthentication, TenantJWTAAuthentication
from central_hub.capabilities import get_effective_capabilities
from central_hub.rbac import RequireHumanUser, user_has_role
from central_hub.api.users.serializers import MoioUserReadSerializer
from central_hub.api.users.views import HasCapability
from central_hub.api.users.serializers import MoioUserWriteSerializer, _resolve_role
from central_hub.api.platform_bootstrap import (
    _notification_settings_payload,
    get_platform_notification_settings,
)
from tenancy.tenant_support import public_schema_name, tenant_schema_context, tenants_enabled
from agent_console.models import AgentConsoleWorkspace, AgentConsoleWorkspaceSkill, AgentConsolePluginAssignment
from agent_console.runtime.config import load_config
from agent_console.runtime.plugins import discover_plugin_manifest_paths, load_plugin_manifest
from agent_console.services.runtime_service import _runtime_config_path

UserModel = get_user_model()


def _tenant_slug(user) -> str:
    tenant = getattr(user, "tenant", None)
    if tenant is None:
        return ""
    return str(getattr(tenant, "schema_name", "") or getattr(tenant, "subdomain", "") or tenant.pk or "").strip().lower() or ""


def _tenant_pk(user):
    tenant = getattr(user, "tenant", None)
    return tenant.pk if tenant else None


def _role_for_frontend(user) -> str:
    """Map backend role to tenant-admin payload role: admin | member | viewer."""
    if getattr(user, "is_superuser", False) or user_has_role(user, "platform_admin"):
        return "admin"
    if user_has_role(user, "tenant_admin"):
        return "admin"
    if user_has_role(user, "viewer"):
        return "viewer"
    return "member"


def _display_name_for_frontend(user) -> str:
    first_name = (getattr(user, "first_name", "") or "").strip()
    last_name = (getattr(user, "last_name", "") or "").strip()
    username = (getattr(user, "username", "") or "").strip()
    email = (getattr(user, "email", "") or "").strip()

    if first_name and last_name:
        return f"{first_name} {last_name}".strip()
    return first_name or last_name or username or email


def _workspace_payload_for_tenant_schema(tenant_schema: str) -> list[dict]:
    rows: list[dict] = []
    try:
        with tenant_schema_context(tenant_schema):
            workspaces = list(AgentConsoleWorkspace.objects.all().order_by("slug"))
            if not workspaces:
                ws = AgentConsoleWorkspace.objects.create(
                    slug="main",
                    name="Main",
                )
                workspaces = [ws]
            for ws in workspaces:
                enabled_skill_keys = list(
                    AgentConsoleWorkspaceSkill.objects.filter(workspace=ws, enabled=True)
                    .order_by("skill_id")
                    .values_list("skill_id", flat=True)
                )
                settings_payload = ws.settings if isinstance(ws.settings, dict) else {}
                tool_allowlist = settings_payload.get("toolAllowlist")
                tool_allowlist = (
                    [str(item).strip() for item in tool_allowlist if str(item).strip()]
                    if isinstance(tool_allowlist, list)
                    else []
                )
                display_name = (ws.name or ws.slug or "").strip() or "Main"
                rows.append(
                    {
                        "id": str(ws.pk),
                        "slug": (ws.slug or "main").strip().lower() or "main",
                        "name": display_name,
                        "displayName": display_name,
                        "specialtyPrompt": (ws.specialty_prompt or "").strip(),
                        "enabledSkillKeys": [str(key).strip() for key in enabled_skill_keys if str(key).strip()],
                        "defaultVendor": (ws.default_vendor or "").strip().lower(),
                        "defaultModel": (ws.default_model or "").strip(),
                        "defaultThinking": (ws.default_thinking or "").strip().lower(),
                        "defaultVerbosity": (ws.default_verbosity or "").strip().lower(),
                        "toolAllowlist": tool_allowlist,
                        "isActive": True,
                    }
                )
    except (ProgrammingError, OperationalError):
        rows = []
    if not rows:
        rows = [
            {
                "id": "",
                "slug": "main",
                "name": "Main",
                "displayName": "Main",
                "specialtyPrompt": "",
                "enabledSkillKeys": [],
                "defaultVendor": "",
                "defaultModel": "",
                "defaultThinking": "",
                "defaultVerbosity": "",
                "toolAllowlist": [],
                "isActive": True,
            }
        ]
    return rows


class TenantBootstrapView(APIView):
    """
    GET /api/tenant/bootstrap/
    Query: workspace (optional), workspaceId (optional)
    Returns tenant-admin payload: tenant, workspace, role, currentUser, users, and empty
    workspaces/skills/automations/integrations/plugins (those live in agent console runtime).
    """
    authentication_classes = [
        CsrfExemptSessionAuthentication,
        TenantJWTAAuthentication,
        BearerTokenAuthentication,
        JWTAuthentication,
    ]
    permission_classes = [IsAuthenticated, RequireHumanUser]

    def get(self, request):
        user = request.user
        tenant = getattr(user, "tenant", None)
        if tenant is None:
            return Response(
                {"ok": False, "error": {"code": "tenant_required", "message": "User must belong to a tenant."}},
                status=status.HTTP_403_FORBIDDEN,
            )

        requested_workspace = (request.query_params.get("workspace") or "").strip().lower()
        requested_workspace_id = (request.query_params.get("workspaceId") or "").strip()
        slug = _tenant_slug(user)
        tenant_pk = _tenant_pk(user)
        tenant_schema = str(getattr(tenant, "schema_name", "") or "").strip().lower()
        workspaces = _workspace_payload_for_tenant_schema(tenant_schema)
        selected_workspace = None
        if requested_workspace_id:
            selected_workspace = next((row for row in workspaces if row.get("id") == requested_workspace_id), None)
        if selected_workspace is None and requested_workspace:
            selected_workspace = next((row for row in workspaces if row.get("slug") == requested_workspace), None)
        if selected_workspace is None:
            selected_workspace = next((row for row in workspaces if row.get("slug") == "main"), None) or (workspaces[0] if workspaces else None)
        workspace = str((selected_workspace or {}).get("slug") or "main").strip().lower() or "main"
        workspace_uuid = str((selected_workspace or {}).get("id") or "").strip()

        # List users in same tenant (same permission as users_manage for list)
        users_qs = UserModel.objects.filter(tenant=tenant).order_by("id")
        users_list = []
        for u in users_qs:
            role = _resolve_role(u)
            frontend_role = "admin" if role == "tenant_admin" else ("viewer" if role == "viewer" else "member")
            users_list.append({
                "id": u.pk,
                "email": getattr(u, "email", "") or "",
                "displayName": _display_name_for_frontend(u),
                "isActive": getattr(u, "is_active", True),
                "role": frontend_role,
                "membershipActive": getattr(u, "is_active", True),
            })

        if tenants_enabled():
            with tenant_schema_context(public_schema_name()):
                notif = get_platform_notification_settings()
        else:
            notif = get_platform_notification_settings()
        notification_settings = _notification_settings_payload(notif)

        payload = {
            "tenant": slug,
            "tenantUuid": str(tenant_pk) if tenant_pk else "",
            "workspace": workspace,
            "workspaceUuid": "",
            "role": _role_for_frontend(user),
            "currentUser": {
                "id": getattr(user, "pk", 0),
                "email": getattr(user, "email", "") or "",
                "displayName": _display_name_for_frontend(user),
            },
            "users": users_list,
            "skills": {
                "tenant": slug,
                "role": _role_for_frontend(user),
                "workspace": workspace,
                "enabledSkillKeys": [],
                "globalSkills": [],
                "tenantSkills": [],
                "mergedSkills": [],
                "enabledSkills": [],
            },
            "workspaces": workspaces,
            "automations": {
                "workspace": workspace,
                "workspaceId": workspace_uuid,
                "templates": [],
                "instances": [],
                "runLogs": [],
            },
            "integrations": [],
            "tenantIntegrations": [],
            "pluginSync": {"syncedCount": 0, "invalid": []},
            "plugins": [],
            "tenantPlugins": [],
            "tenantPluginAssignments": [],
            "workspaceUuid": workspace_uuid,
            "notificationSettings": notification_settings,
        }
        return Response({"ok": True, "payload": payload})


class TenantUsersSaveView(APIView):
    """
    POST /api/tenant/users/
    Body: email, displayName?, password?, role (admin|member|viewer), isActive?, membershipActive?
    Create or update a tenant user. Idempotent by email within tenant.
    """
    authentication_classes = [
        CsrfExemptSessionAuthentication,
        TenantJWTAAuthentication,
        BearerTokenAuthentication,
        JWTAuthentication,
    ]
    permission_classes = [IsAuthenticated, RequireHumanUser, HasCapability]

    def post(self, request):
        data = request.data or {}
        email = (data.get("email") or "").strip().lower()
        if not email:
            return Response(
                {"ok": False, "error": {"code": "validation_error", "message": "email is required"}},
                status=status.HTTP_400_BAD_REQUEST,
            )
        tenant = getattr(request.user, "tenant", None)
        if tenant is None:
            return Response(
                {"ok": False, "error": {"code": "tenant_required", "message": "Authenticated user must belong to a tenant."}},
                status=status.HTTP_403_FORBIDDEN,
            )

        display_name = (data.get("displayName") or "").strip()
        role_raw = (data.get("role") or "member").strip().lower()
        if role_raw not in ("admin", "member", "viewer"):
            role_raw = "member"
        role = "tenant_admin" if role_raw == "admin" else role_raw
        is_active = data.get("isActive", True) if data.get("isActive") is not None else True
        password = (data.get("password") or "").strip() or None

        existing = UserModel.objects.filter(tenant=tenant, email__iexact=email).first()
        username = email or "user"
        if existing:
            update_data = {
                "email": email,
                "username": getattr(existing, "username", "") or username,
                "first_name": display_name,
                "last_name": "",
                "is_active": is_active,
                "role": role,
            }
            if password:
                update_data["password"] = password
            serializer = MoioUserWriteSerializer(
                existing,
                data=update_data,
                partial=True,
                context={"request": request},
            )
            if not serializer.is_valid():
                return Response(
                    {"ok": False, "error": {"code": "validation_error", "message": str(serializer.errors)}},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            user = serializer.save()
        else:
            if not password:
                return Response(
                    {"ok": False, "error": {"code": "validation_error", "message": "password is required for new users"}},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            serializer = MoioUserWriteSerializer(
                data={
                    "email": email,
                    "username": email,
                    "first_name": display_name,
                    "last_name": "",
                    "is_active": is_active,
                    "role": role,
                    "password": password,
                },
                context={"request": request},
            )
            if not serializer.is_valid():
                return Response(
                    {"ok": False, "error": {"code": "validation_error", "message": str(serializer.errors)}},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            user = serializer.save()

        return Response({
            "ok": True,
            "payload": MoioUserReadSerializer(user, context={"request": request}).data,
        })


class TenantUsersDeleteView(APIView):
    """
    POST /api/tenant/users/delete/
    Body: id? or email?
    Delete a tenant user. Requester cannot delete self.
    """
    authentication_classes = [
        CsrfExemptSessionAuthentication,
        TenantJWTAAuthentication,
        BearerTokenAuthentication,
        JWTAuthentication,
    ]
    permission_classes = [IsAuthenticated, RequireHumanUser, HasCapability]

    def post(self, request):
        data = request.data or {}
        user_id = data.get("id")
        email = (data.get("email") or "").strip().lower()
        if not user_id and not email:
            return Response(
                {"ok": False, "error": {"code": "validation_error", "message": "id or email is required"}},
                status=status.HTTP_400_BAD_REQUEST,
            )
        tenant = getattr(request.user, "tenant", None)
        if tenant is None:
            return Response(
                {"ok": False, "error": {"code": "tenant_required", "message": "Authenticated user must belong to a tenant."}},
                status=status.HTTP_403_FORBIDDEN,
            )

        if user_id:
            target = UserModel.objects.filter(tenant=tenant, pk=user_id).first()
        else:
            target = UserModel.objects.filter(tenant=tenant, email__iexact=email).first()

        if target is None:
            return Response(
                {"ok": True, "payload": {"deleted": False, "message": "User not found in this tenant."}},
            )

        if target.pk == request.user.pk:
            return Response(
                {"ok": False, "error": {"code": "permission_denied", "message": "You cannot delete your own user."}},
                status=status.HTTP_403_FORBIDDEN,
            )

        target.delete()
        return Response({"ok": True, "payload": {"deleted": True}})


def _can_manage_workspaces(user) -> bool:
    if getattr(user, "is_superuser", False) or user_has_role(user, "platform_admin"):
        return True
    return user_has_role(user, "tenant_admin")


def _normalize_skill_keys(raw_keys) -> list[str]:
    if not isinstance(raw_keys, list):
        return []
    out: list[str] = []
    seen: set[str] = set()
    for raw in raw_keys:
        key = str(raw or "").strip()
        if not key:
            continue
        if key in seen:
            continue
        seen.add(key)
        out.append(key)
    return out


def _workspace_payload(ws: AgentConsoleWorkspace) -> dict:
    enabled_skill_keys = list(
        AgentConsoleWorkspaceSkill.objects.filter(workspace=ws, enabled=True)
        .order_by("skill_id")
        .values_list("skill_id", flat=True)
    )
    settings_payload = ws.settings if isinstance(ws.settings, dict) else {}
    tool_allowlist = settings_payload.get("toolAllowlist")
    tool_allowlist = (
        [str(item).strip() for item in tool_allowlist if str(item).strip()]
        if isinstance(tool_allowlist, list)
        else []
    )
    display_name = (ws.name or ws.slug or "").strip() or "Main"
    return {
        "id": str(ws.pk),
        "slug": (ws.slug or "main").strip().lower() or "main",
        "name": display_name,
        "displayName": display_name,
        "specialtyPrompt": (ws.specialty_prompt or "").strip(),
        "enabledSkillKeys": [str(key).strip() for key in enabled_skill_keys if str(key).strip()],
        "defaultVendor": (ws.default_vendor or "").strip().lower(),
        "defaultModel": (ws.default_model or "").strip(),
        "defaultThinking": (ws.default_thinking or "").strip().lower(),
        "defaultVerbosity": (ws.default_verbosity or "").strip().lower(),
        "toolAllowlist": tool_allowlist,
        "isActive": True,
    }


class TenantWorkspacesSaveView(APIView):
    """
    POST /api/tenant/workspaces/
    Body: id?, slug, name?, displayName?, specialtyPrompt?, defaultVendor?,
          defaultModel?, defaultThinking?, defaultVerbosity?, toolAllowlist?, enabledSkillKeys?, isActive?
    """
    authentication_classes = [
        CsrfExemptSessionAuthentication,
        TenantJWTAAuthentication,
        BearerTokenAuthentication,
        JWTAuthentication,
    ]
    permission_classes = [IsAuthenticated, RequireHumanUser]

    def post(self, request):
        user = request.user
        if not _can_manage_workspaces(user):
            return Response(
                {"ok": False, "error": {"code": "permission_denied", "message": "Workspace management requires tenant admin."}},
                status=status.HTTP_403_FORBIDDEN,
            )

        tenant = getattr(user, "tenant", None)
        if tenant is None:
            return Response(
                {"ok": False, "error": {"code": "tenant_required", "message": "Authenticated user must belong to a tenant."}},
                status=status.HTTP_403_FORBIDDEN,
            )

        data = request.data or {}
        workspace_id = str(data.get("id") or "").strip()
        slug = str(data.get("slug") or "").strip().lower()
        name = str(data.get("name") or data.get("displayName") or "").strip()
        if not slug and not workspace_id:
            return Response(
                {"ok": False, "error": {"code": "validation_error", "message": "slug is required"}},
                status=status.HTTP_400_BAD_REQUEST,
            )

        tenant_schema = str(getattr(tenant, "schema_name", "") or "").strip().lower()
        with tenant_schema_context(tenant_schema):
            workspace = None
            if workspace_id:
                workspace = AgentConsoleWorkspace.objects.filter(pk=workspace_id).first()
            if workspace is None and slug:
                workspace = AgentConsoleWorkspace.objects.filter(slug=slug).first()
            if workspace is None:
                if not slug:
                    return Response(
                        {"ok": False, "error": {"code": "validation_error", "message": "slug is required for new workspace"}},
                        status=status.HTTP_400_BAD_REQUEST,
                    )
                workspace = AgentConsoleWorkspace(slug=slug)
            elif slug and slug != (workspace.slug or "").strip().lower():
                if AgentConsoleWorkspace.objects.filter(slug=slug).exclude(pk=workspace.pk).exists():
                    return Response(
                        {"ok": False, "error": {"code": "validation_error", "message": "workspace slug already exists"}},
                        status=status.HTTP_400_BAD_REQUEST,
                    )
                workspace.slug = slug

            workspace.name = name or slug or workspace.slug or "main"
            workspace.specialty_prompt = str(data.get("specialtyPrompt") or "").strip()
            workspace.default_vendor = str(data.get("defaultVendor") or "").strip().lower()
            workspace.default_model = str(data.get("defaultModel") or "").strip()
            workspace.default_thinking = str(data.get("defaultThinking") or "").strip().lower()
            workspace.default_verbosity = str(data.get("defaultVerbosity") or "").strip().lower()
            settings_payload = workspace.settings if isinstance(workspace.settings, dict) else {}
            raw_tool_allowlist = data.get("toolAllowlist")
            if isinstance(raw_tool_allowlist, list):
                settings_payload["toolAllowlist"] = [
                    str(item).strip() for item in raw_tool_allowlist if str(item).strip()
                ]
            workspace.settings = settings_payload
            workspace.save()

            selected_keys = _normalize_skill_keys(data.get("enabledSkillKeys"))
            AgentConsoleWorkspaceSkill.objects.filter(workspace=workspace).exclude(skill_id__in=selected_keys).update(enabled=False)
            for key in selected_keys:
                AgentConsoleWorkspaceSkill.objects.update_or_create(
                    workspace=workspace,
                    skill_id=key,
                    defaults={"enabled": True},
                )

            payload = _workspace_payload(workspace)
        return Response({"ok": True, "payload": payload})


class TenantWorkspacesDeleteView(APIView):
    """
    POST /api/tenant/workspaces/delete/
    Body: id? or slug?
    """
    authentication_classes = [
        CsrfExemptSessionAuthentication,
        TenantJWTAAuthentication,
        BearerTokenAuthentication,
        JWTAuthentication,
    ]
    permission_classes = [IsAuthenticated, RequireHumanUser]

    def post(self, request):
        user = request.user
        if not _can_manage_workspaces(user):
            return Response(
                {"ok": False, "error": {"code": "permission_denied", "message": "Workspace management requires tenant admin."}},
                status=status.HTTP_403_FORBIDDEN,
            )

        tenant = getattr(user, "tenant", None)
        if tenant is None:
            return Response(
                {"ok": False, "error": {"code": "tenant_required", "message": "Authenticated user must belong to a tenant."}},
                status=status.HTTP_403_FORBIDDEN,
            )

        data = request.data or {}
        workspace_id = str(data.get("id") or "").strip()
        slug = str(data.get("slug") or "").strip().lower()
        if not workspace_id and not slug:
            return Response(
                {"ok": False, "error": {"code": "validation_error", "message": "id or slug is required"}},
                status=status.HTTP_400_BAD_REQUEST,
            )

        tenant_schema = str(getattr(tenant, "schema_name", "") or "").strip().lower()
        with tenant_schema_context(tenant_schema):
            workspace = None
            if workspace_id:
                workspace = AgentConsoleWorkspace.objects.filter(pk=workspace_id).first()
            if workspace is None and slug:
                workspace = AgentConsoleWorkspace.objects.filter(slug=slug).first()
            if workspace is None:
                return Response({"ok": True, "payload": {"deleted": False, "message": "Workspace not found."}})
            if (workspace.slug or "").strip().lower() == "main":
                return Response(
                    {"ok": False, "error": {"code": "validation_error", "message": "main workspace cannot be deleted"}},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            workspace.delete()
        return Response({"ok": True, "payload": {"deleted": True}})


def _load_runtime_config_for_plugins():
    config_path = _runtime_config_path()
    previous_model_api_key = os.environ.get("REPLICA_MODEL_API_KEY")
    try:
        if not previous_model_api_key:
            os.environ["REPLICA_MODEL_API_KEY"] = "plugin-scan-placeholder"
        return load_config(config_path)
    finally:
        if previous_model_api_key is None:
            os.environ.pop("REPLICA_MODEL_API_KEY", None)
        else:
            os.environ["REPLICA_MODEL_API_KEY"] = previous_model_api_key


def _plugin_registry_entries(config) -> list[dict]:
    manifests_dir = getattr(config.plugins, "manifests_dir", None)
    extra_dirs = list(getattr(config.plugins, "additional_manifests_dirs", []) or [])
    scan_roots = [manifests_dir, *extra_dirs]
    seen: set[str] = set()
    entries: list[dict] = []
    approved = {str(item or "").strip().lower() for item in getattr(config.plugins, "platform_approved", []) if str(item or "").strip()}
    for root in scan_roots:
        if not root:
            continue
        for manifest_path in discover_plugin_manifest_paths(root):
            try:
                manifest = load_plugin_manifest(manifest_path)
            except Exception:
                continue
            plugin_id = str(manifest.plugin_id or "").strip().lower()
            if not plugin_id or plugin_id in seen:
                continue
            seen.add(plugin_id)
            entries.append(
                {
                    "pluginId": plugin_id,
                    "name": str(manifest.name or plugin_id),
                    "version": str(manifest.version or ""),
                    "description": str(manifest.description or ""),
                    "bundleSha256": "",
                    "hasBundleBlob": False,
                    "iconDataUrl": "",
                    "iconFallback": "",
                    "helpMarkdown": "",
                    "manifest": manifest.to_dict(),
                    "capabilities": list(manifest.capabilities),
                    "permissions": list(manifest.permissions),
                    "isValidated": True,
                    "isPlatformApproved": plugin_id in approved,
                    "validationError": "",
                    "updatedAt": "",
                }
            )
    return sorted(entries, key=lambda row: str(row.get("pluginId", "")))


def _resolve_workspace_for_plugin_ops(tenant_schema: str, workspace_slug: str, workspace_id: str) -> AgentConsoleWorkspace:
    with tenant_schema_context(tenant_schema):
        workspace = None
        if workspace_id:
            workspace = AgentConsoleWorkspace.objects.filter(pk=workspace_id).first()
        if workspace is None and workspace_slug:
            workspace = AgentConsoleWorkspace.objects.filter(slug=workspace_slug).first()
        if workspace is None:
            workspace = AgentConsoleWorkspace.objects.filter(slug="main").first()
        if workspace is None:
            workspace = AgentConsoleWorkspace.objects.create(slug="main", name="Main")
        return workspace


def _tenant_plugin_state_payload(*, user, tenant_schema: str, workspace_slug: str = "main", workspace_id: str = "") -> dict:
    config = _load_runtime_config_for_plugins()
    role = _role_for_frontend(user)
    tenant_slug = _tenant_slug(user)
    tenant_bindings: list[dict] = []
    assignment_rows: list[dict] = []
    workspace = _resolve_workspace_for_plugin_ops(tenant_schema, workspace_slug, workspace_id)
    with tenant_schema_context(tenant_schema):
        assignments = list(AgentConsolePluginAssignment.objects.filter(workspace=workspace).order_by("plugin_id"))
        for row in assignments:
            plugin_id = str(row.plugin_id or "").strip().lower()
            allowlist = list(row.user_allowlist) if isinstance(row.user_allowlist, list) else []
            tenant_bindings.append(
                {
                    "tenantSlug": tenant_slug,
                    "pluginId": plugin_id,
                    "isEnabled": True,
                    "pluginConfig": {},
                    "notes": "",
                    "updatedAt": "",
                }
            )
            for item in allowlist:
                token = str(item or "").strip().lower()
                if not token:
                    continue
                if token in {"admin", "member", "viewer"}:
                    assignment_rows.append(
                        {
                            "tenantSlug": tenant_slug,
                            "pluginId": plugin_id,
                            "assignmentType": "role",
                            "role": token,
                            "userId": 0,
                            "userEmail": "",
                            "isActive": True,
                            "notes": "",
                            "updatedAt": "",
                        }
                    )
                else:
                    assignment_rows.append(
                        {
                            "tenantSlug": tenant_slug,
                            "pluginId": plugin_id,
                            "assignmentType": "user",
                            "role": "",
                            "userId": 0,
                            "userEmail": token,
                            "isActive": True,
                            "notes": "",
                            "updatedAt": "",
                        }
                    )
    return {
        "tenant": tenant_slug,
        "role": role,
        "isTenantAdmin": role == "admin",
        "sync": {"syncedCount": 0, "invalid": []},
        "plugins": _plugin_registry_entries(config),
        "tenantPlugins": tenant_bindings,
        "tenantPluginAssignments": assignment_rows,
    }


class TenantPluginsView(APIView):
    """
    GET/POST /api/tenant/plugins/
    """
    authentication_classes = [
        CsrfExemptSessionAuthentication,
        TenantJWTAAuthentication,
        BearerTokenAuthentication,
        JWTAuthentication,
    ]
    permission_classes = [IsAuthenticated, RequireHumanUser]

    def get(self, request):
        user = request.user
        tenant = getattr(user, "tenant", None)
        if tenant is None:
            return Response(
                {"ok": False, "error": {"code": "tenant_required", "message": "Authenticated user must belong to a tenant."}},
                status=status.HTTP_403_FORBIDDEN,
            )
        workspace_slug = (request.query_params.get("workspace") or request.headers.get("X-Workspace") or "main").strip().lower() or "main"
        workspace_id = (request.query_params.get("workspaceId") or request.headers.get("X-Workspace-Id") or "").strip()
        tenant_schema = str(getattr(tenant, "schema_name", "") or "").strip().lower()
        payload = _tenant_plugin_state_payload(
            user=user,
            tenant_schema=tenant_schema,
            workspace_slug=workspace_slug,
            workspace_id=workspace_id,
        )
        return Response({"ok": True, "payload": payload})

    def post(self, request):
        user = request.user
        if not _can_manage_workspaces(user):
            return Response(
                {"ok": False, "error": {"code": "permission_denied", "message": "Plugin management requires tenant admin."}},
                status=status.HTTP_403_FORBIDDEN,
            )
        tenant = getattr(user, "tenant", None)
        if tenant is None:
            return Response(
                {"ok": False, "error": {"code": "tenant_required", "message": "Authenticated user must belong to a tenant."}},
                status=status.HTTP_403_FORBIDDEN,
            )
        data = request.data or {}
        plugin_id = str(data.get("pluginId") or "").strip().lower()
        if not plugin_id:
            return Response(
                {"ok": False, "error": {"code": "validation_error", "message": "pluginId is required"}},
                status=status.HTTP_400_BAD_REQUEST,
            )
        is_enabled = bool(data.get("isEnabled", True))
        workspace_slug = (request.query_params.get("workspace") or request.headers.get("X-Workspace") or "main").strip().lower() or "main"
        workspace_id = (request.query_params.get("workspaceId") or request.headers.get("X-Workspace-Id") or "").strip()
        tenant_schema = str(getattr(tenant, "schema_name", "") or "").strip().lower()
        workspace = _resolve_workspace_for_plugin_ops(tenant_schema, workspace_slug, workspace_id)

        with tenant_schema_context(tenant_schema):
            if not is_enabled:
                AgentConsolePluginAssignment.objects.filter(workspace=workspace, plugin_id=plugin_id).delete()
            else:
                assignment_tokens: list[str] = []
                raw_assignments = data.get("assignments")
                rows = raw_assignments if isinstance(raw_assignments, list) else []
                for row in rows:
                    if not isinstance(row, dict):
                        continue
                    if row.get("isActive") is False:
                        continue
                    assignment_type = str(row.get("assignmentType") or "role").strip().lower()
                    if assignment_type == "user":
                        email = str(row.get("userEmail") or "").strip().lower()
                        if email:
                            assignment_tokens.append(email)
                    else:
                        role = str(row.get("role") or "member").strip().lower()
                        if role in {"admin", "member", "viewer"}:
                            assignment_tokens.append(role)
                deduped = []
                seen = set()
                for token in assignment_tokens:
                    if token in seen:
                        continue
                    seen.add(token)
                    deduped.append(token)
                AgentConsolePluginAssignment.objects.update_or_create(
                    workspace=workspace,
                    plugin_id=plugin_id,
                    defaults={"user_allowlist": deduped},
                )

        payload = _tenant_plugin_state_payload(
            user=user,
            tenant_schema=tenant_schema,
            workspace_slug=workspace_slug,
            workspace_id=workspace_id,
        )
        return Response({"ok": True, "payload": payload})
