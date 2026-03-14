"""
GET /api/platform/bootstrap/ — legacy Platform Admin UI bootstrap payload.
Requires JWT (same as main app) and is_staff or is_superuser.
Returns { "ok": true, "payload": BootstrapPayload } so the legacy app can load.
"""
from __future__ import annotations

from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.authentication import JWTAuthentication

from central_hub.api.platform.plugin_admin_state import platform_plugin_admin_state
from central_hub.authentication import TenantJWTAAuthentication
from central_hub.models import Plan, PlatformConfiguration, PlatformNotificationSettings
from moio_platform.authentication import BearerTokenAuthentication
from tenancy.models import IntegrationDefinition, Tenant, TenantIntegration
from tenancy.tenant_support import public_schema_name, tenant_schema_context, tenants_enabled

UserModel = get_user_model()

MODULE_ENABLEMENT_DEFAULTS = {
    "crm": True,
    "flowsDatalab": False,
    "chatbot": False,
    "agentConsole": False,
}


def _tenant_module_enablements(tenant: Tenant) -> dict:
    """
    Normalize module enablements for Platform Admin.

    Source of truth is tenant.features with optional tenant.ui override:
      - crm -> features.crm (defaults true)
      - flowsDatalab -> features.flows or features.datalab
      - chatbot -> features.chatbot
      - agentConsole -> features.agent_console
    """
    features = getattr(tenant, "features", None) or {}
    ui = getattr(tenant, "ui", None) or {}
    ui_enablements = ui.get("module_enablements") if isinstance(ui, dict) else None

    normalized = dict(MODULE_ENABLEMENT_DEFAULTS)
    normalized["crm"] = bool(features.get("crm", True))
    normalized["flowsDatalab"] = bool(features.get("flows", False) or features.get("datalab", False))
    normalized["chatbot"] = bool(features.get("chatbot", False))
    normalized["agentConsole"] = bool(features.get("agent_console", False))

    if isinstance(ui_enablements, dict):
        for key in MODULE_ENABLEMENT_DEFAULTS:
            if key in ui_enablements:
                normalized[key] = bool(ui_enablements[key])

    # CRM is always base.
    normalized["crm"] = True
    return normalized


def _platform_configuration_payload(cfg: PlatformConfiguration | None, request=None) -> dict | None:
    """Serialize PlatformConfiguration for Platform Admin. Secrets are included (admin-only)."""
    if cfg is None:
        return None
    logo_url = ""
    favicon_url = ""
    if request and getattr(cfg, "logo", None) and cfg.logo:
        logo_url = request.build_absolute_uri(cfg.logo.url)
    if request and getattr(cfg, "favicon", None) and cfg.favicon:
        favicon_url = request.build_absolute_uri(cfg.favicon.url)
    return {
        "siteName": getattr(cfg, "site_name", None) or "",
        "company": getattr(cfg, "company", None) or "",
        "myUrl": getattr(cfg, "my_url", None) or "",
        "logoUrl": logo_url,
        "faviconUrl": favicon_url,
        "whatsappWebhookToken": getattr(cfg, "whatsapp_webhook_token", None) or "",
        "whatsappWebhookRedirect": getattr(cfg, "whatsapp_webhook_redirect", None) or "",
        "fbSystemToken": getattr(cfg, "fb_system_token", None) or "",
        "fbMoioBotAppId": getattr(cfg, "fb_moio_bot_app_id", None) or "",
        "fbMoioBusinessManagerId": getattr(cfg, "fb_moio_business_manager_id", None) or "",
        "fbMoioBotAppSecret": getattr(cfg, "fb_moio_bot_app_secret", None) or "",
        "fbMoioBotConfigurationId": getattr(cfg, "fb_moio_bot_configuration_id", None) or "",
        "googleOauthClientId": getattr(cfg, "google_oauth_client_id", None) or "",
        "googleOauthClientSecret": getattr(cfg, "google_oauth_client_secret", None) or "",
        "microsoftOauthClientId": getattr(cfg, "microsoft_oauth_client_id", None) or "",
        "microsoftOauthClientSecret": getattr(cfg, "microsoft_oauth_client_secret", None) or "",
        "shopifyClientId": getattr(cfg, "shopify_client_id", None) or "",
        "shopifyClientSecret": getattr(cfg, "shopify_client_secret", None) or "",
    }


def _current_user_payload(user) -> dict | None:
    if not user:
        return None
    display = (getattr(user, "first_name", "") or "").strip() or (getattr(user, "username", "") or "")
    if (getattr(user, "last_name", "") or "").strip():
        display = f"{display} {(user.last_name or '').strip()}".strip()
    return {
        "id": getattr(user, "id", 0),
        "email": getattr(user, "email", "") or "",
        "displayName": display or getattr(user, "username", "") or "Platform Admin",
        "isPlatformAdmin": bool(getattr(user, "is_staff", False) or getattr(user, "is_superuser", False)),
        "isActive": bool(getattr(user, "is_active", True)),
    }


def _plan_payload(p: Plan) -> dict:
    return {
        "id": str(p.pk),
        "key": getattr(p, "key", "") or "",
        "name": getattr(p, "name", "") or "",
        "displayOrder": getattr(p, "display_order", 0),
        "isActive": bool(getattr(p, "is_active", True)),
        "pricingPolicy": getattr(p, "pricing_policy", None) or {},
        "entitlementPolicy": getattr(p, "entitlement_policy", None) or {},
    }


def _tenant_payload(t: Tenant) -> dict:
    return {
        "id": str(t.pk),
        "uuid": str(getattr(t, "tenant_code", t.pk)),
        "name": getattr(t, "nombre", "") or "",
        "slug": getattr(t, "schema_name", "") or "",
        "schemaName": getattr(t, "schema_name", "") or "",
        "isActive": bool(getattr(t, "enabled", True)),
        "primaryDomain": getattr(t, "primary_domain", "") or "",
        "plan": str(getattr(t, "plan", "free") or "free"),
        "moduleEnablements": _tenant_module_enablements(t),
    }


def _platform_user_payload(u) -> dict:
    display = (getattr(u, "first_name", "") or "").strip() or (getattr(u, "username", "") or "")
    if (getattr(u, "last_name", "") or "").strip():
        display = f"{display} {(u.last_name or '').strip()}".strip()
    display = display or getattr(u, "username", "") or u.email or ""
    tenant = getattr(u, "tenant", None)
    # Role: admin if in tenant_admin group or superuser, else member
    try:
        group_names = [g.name for g in (u.groups.all() if hasattr(u, "groups") else [])]
    except Exception:
        group_names = []
    is_tenant_admin = getattr(u, "is_superuser", False) or "tenant_admin" in group_names
    tenant_memberships = []
    if tenant:
        tenant_memberships.append({
            "tenantSlug": getattr(tenant, "schema_name", "") or "",
            "role": "admin" if is_tenant_admin else "member",
            "isActive": bool(getattr(u, "is_active", True)),
        })
    return {
        "id": getattr(u, "id", 0),
        "email": getattr(u, "email", "") or "",
        "displayName": display,
        "isPlatformAdmin": bool(getattr(u, "is_staff", False) or getattr(u, "is_superuser", False)),
        "isActive": bool(getattr(u, "is_active", True)),
        "lastLoginAt": (u.last_login.isoformat() if getattr(u, "last_login", None) else "") or "",
        "tenantMemberships": tenant_memberships,
    }


def _hub_integrations_payload() -> list[dict]:
    """Integrations Hub contract: list from central_hub registry for catalog/control plane."""
    try:
        from central_hub.integrations.registry import list_integrations
        definitions = list_integrations()
        return [
            {
                "slug": d.slug,
                "name": d.name,
                "description": d.description,
                "category": d.category,
                "icon": d.icon,
                "supportsMultiInstance": d.supports_multi_instance,
                "authScope": getattr(d, "auth_scope", "tenant"),
                "supportsWebhook": getattr(d, "supports_webhook", False),
                "supportsOauth": getattr(d, "supports_oauth", False),
                "webhookPathSuffix": getattr(d, "webhook_path_suffix", "") or "",
            }
            for d in definitions
        ]
    except Exception:
        return []


def _integration_definition_payload(i: IntegrationDefinition) -> dict:
    return {
        "id": i.pk,
        "key": getattr(i, "key", "") or "",
        "name": getattr(i, "name", "") or "",
        "category": getattr(i, "category", "") or "",
        "baseUrl": getattr(i, "base_url", "") or "",
        "openapiUrl": getattr(i, "openapi_url", "") or "",
        "defaultAuthType": getattr(i, "default_auth_type", "bearer") or "bearer",
        "authScope": getattr(i, "auth_scope", "tenant") or "tenant",
        "authConfigSchema": getattr(i, "auth_config_schema", None) or {},
        "globalAuthConfig": getattr(i, "global_auth_config", None) or {},
        "globalAuthConfigured": bool(getattr(i, "global_auth_config", None)),
        "assistantDocsMarkdown": getattr(i, "assistant_docs_markdown", "") or "",
        "defaultHeaders": getattr(i, "default_headers", None) or {},
        "isActive": bool(getattr(i, "is_active", True)),
        "metadata": getattr(i, "metadata", None) or {},
    }


def _notification_settings_payload(settings: PlatformNotificationSettings | None) -> dict:
    """Serialize PlatformNotificationSettings for Platform Admin and main app (camelCase)."""
    if settings is None:
        return {
            "title": "Moio",
            "iconUrl": "",
            "badgeUrl": "",
            "requireInteraction": False,
            "renotify": False,
            "silent": True,
            "testTitle": "Moio test notification",
            "testBody": "Notifications are configured for this browser.",
        }
    return {
        "title": getattr(settings, "title", "") or "Moio",
        "iconUrl": getattr(settings, "icon_url", "") or "",
        "badgeUrl": getattr(settings, "badge_url", "") or "",
        "requireInteraction": bool(getattr(settings, "require_interaction", False)),
        "renotify": bool(getattr(settings, "renotify", False)),
        "silent": bool(getattr(settings, "silent", False)),
        "testTitle": getattr(settings, "test_title", "") or "Moio test notification",
        "testBody": getattr(settings, "test_body", "") or "Notifications are configured for this browser.",
    }


def get_platform_notification_settings():
    """Load platform notification settings (singleton). Run in public schema when tenants_enabled."""
    return PlatformNotificationSettings.objects.first()


def _tenant_integration_payload(ti: TenantIntegration) -> dict:
    tenant = getattr(ti, "tenant", None)
    integration = getattr(ti, "integration", None)
    return {
        "id": ti.pk,
        "tenantSlug": getattr(tenant, "schema_name", "") if tenant else "",
        "integrationKey": getattr(integration, "key", "") if integration else "",
        "authScope": getattr(integration, "auth_scope", "tenant") if integration else "tenant",
        "isEnabled": bool(getattr(ti, "is_enabled", True)),
        "notes": getattr(ti, "notes", "") or "",
        "assistantDocsOverride": getattr(ti, "assistant_docs_override", "") or "",
        "tenantAuthConfigured": bool(getattr(ti, "tenant_auth_config", None)),
        "tenantAuthConfig": getattr(ti, "tenant_auth_config", None) or {},
        "updatedAt": (ti.updated_at.isoformat() if getattr(ti, "updated_at", None) else "") or "",
    }


def build_bootstrap_payload(request_user, request=None) -> dict:
    """Build full BootstrapPayload for legacy Platform Admin. Run in public schema when tenants enabled."""
    current_user = _current_user_payload(request_user)
    tenants_list = []
    users_list = []
    integrations_list = []
    tenant_integrations_list = []
    platform_config = None
    plugin_state = {"sync": {"syncedCount": 0, "invalid": []}, "plugins": [], "tenantPlugins": [], "tenantPluginAssignments": []}

    plans_list = []
    if tenants_enabled():
        with tenant_schema_context(public_schema_name()):
            tenants_list = [_tenant_payload(t) for t in Tenant.objects.all().order_by("schema_name")]
            for u in UserModel.objects.all().select_related("tenant").order_by("id"):
                users_list.append(_platform_user_payload(u))
            integrations_list = [_integration_definition_payload(i) for i in IntegrationDefinition.objects.all()]
            for ti in TenantIntegration.objects.select_related("tenant", "integration").all():
                tenant_integrations_list.append(_tenant_integration_payload(ti))
            platform_config = _platform_configuration_payload(PlatformConfiguration.objects.first(), request)
            notif = get_platform_notification_settings()
            plugin_state = platform_plugin_admin_state()
            plans_list = [_plan_payload(p) for p in Plan.objects.filter(is_active=True).order_by("display_order", "key")]
    else:
        tenants_list = [_tenant_payload(t) for t in Tenant.objects.all().order_by("schema_name")]
        for u in UserModel.objects.all().select_related("tenant").order_by("id"):
            users_list.append(_platform_user_payload(u))
        integrations_list = [_integration_definition_payload(i) for i in IntegrationDefinition.objects.all()]
        for ti in TenantIntegration.objects.select_related("tenant", "integration").all():
            tenant_integrations_list.append(_tenant_integration_payload(ti))
        platform_config = _platform_configuration_payload(PlatformConfiguration.objects.first(), request)
        notif = get_platform_notification_settings()
        plugin_state = platform_plugin_admin_state()
        plans_list = [_plan_payload(p) for p in Plan.objects.filter(is_active=True).order_by("display_order", "key")]
    notification_settings = _notification_settings_payload(notif)

    # Integrations Hub contract: catalog from central_hub registry (single source for hub UX)
    hub_integrations_list = _hub_integrations_payload()

    return {
        "tenantsEnabled": True,
        "publicSchema": public_schema_name(),
        "currentUser": current_user,
        "tenants": tenants_list,
        "plans": plans_list,
        "users": users_list,
        "integrations": integrations_list,
        "hubIntegrations": hub_integrations_list,
        "globalSkills": [],
        "tenantIntegrations": tenant_integrations_list,
        "pluginSync": plugin_state.get("sync", {"syncedCount": 0, "invalid": []}),
        "plugins": plugin_state.get("plugins", []),
        "tenantPlugins": plugin_state.get("tenantPlugins", []),
        "tenantPluginAssignments": plugin_state.get("tenantPluginAssignments", []),
        "platformConfiguration": platform_config,
        "notificationSettings": notification_settings,
    }


def _is_platform_admin_user(user) -> bool:
    """Platform admin: superuser or staff with no tenant or public schema only (no tenant access)."""
    if not user or not getattr(user, "is_authenticated", False):
        return False
    if not getattr(user, "is_staff", False) and not getattr(user, "is_superuser", False):
        return False
    tenant = getattr(user, "tenant", None)
    if tenant is None:
        return True
    schema = str(getattr(tenant, "schema_name", "") or "").strip().lower()
    return schema == public_schema_name().lower()


class PlatformBootstrapView(APIView):
    """
    GET /api/platform/bootstrap/
    Legacy Platform Admin bootstrap: currentUser + tenants, users, integrations, tenantIntegrations from DB.
    Only for superuser/staff with no tenant or public schema only (platform-admin only, no tenant access).
    """
    authentication_classes = [
        TenantJWTAAuthentication,
        BearerTokenAuthentication,
        JWTAuthentication,
    ]
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user
        if not _is_platform_admin_user(user):
            return Response(
                {
                    "ok": False,
                    "error": {
                        "message": "Platform admin access required (superuser/staff with no tenant or public schema only).",
                        "code": "forbidden",
                    },
                },
                status=403,
            )
        payload = build_bootstrap_payload(user, request=self.request)
        return Response({"ok": True, "payload": payload})
