"""
Platform Admin API views: POST/delete for tenants, users, integrations, etc.
All require is_staff or is_superuser and return { "ok": true, "payload": BootstrapPayload }.
"""
from __future__ import annotations

from django.contrib.auth import get_user_model
from django.core.management import call_command
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.authentication import JWTAuthentication

from central_hub.api.platform_bootstrap import build_bootstrap_payload, _is_platform_admin_user
from central_hub.authentication import TenantJWTAAuthentication
from central_hub.models import PlatformConfiguration, PlatformNotificationSettings
from moio_platform.authentication import BearerTokenAuthentication
from tenancy.models import IntegrationDefinition, Tenant, TenantDomain, TenantIntegration
from tenancy.tenant_support import public_schema_name, tenant_schema_context, tenants_enabled
from tenancy.validators import validate_subdomain_rfc

UserModel = get_user_model()


def _platform_admin_required(view_method):
    """Decorator: return 403 if request.user is not staff/superuser."""

    def wrapped(self, request, *args, **kwargs):
        user = getattr(request, "user", None)
        if not user or not getattr(user, "is_authenticated", False):
            return Response(
                {"ok": False, "error": {"message": "Authentication required.", "code": "auth_required"}},
                status=status.HTTP_401_UNAUTHORIZED,
            )
        if not getattr(user, "is_staff", False) and not getattr(user, "is_superuser", False):
            return Response(
                {"ok": False, "error": {"message": "Platform admin access required.", "code": "forbidden"}},
                status=status.HTTP_403_FORBIDDEN,
            )
        return view_method(self, request, *args, **kwargs)

    return wrapped


class PlatformAdminMixin:
    """Mixin for platform admin views: same auth as bootstrap + 403 if not staff/superuser."""

    authentication_classes = [
        TenantJWTAAuthentication,
        BearerTokenAuthentication,
        JWTAuthentication,
    ]
    permission_classes = [IsAuthenticated]

    def _check_platform_admin(self, request):
        user = getattr(request, "user", None)
        if not user or not getattr(user, "is_authenticated", False):
            return Response(
                {"ok": False, "error": {"message": "Authentication required.", "code": "auth_required"}},
                status=status.HTTP_401_UNAUTHORIZED,
            )
        if not _is_platform_admin_user(user):
            return Response(
                {
                    "ok": False,
                    "error": {
                        "message": "Platform admin access required (superuser/staff with no tenant or public schema only).",
                        "code": "forbidden",
                    },
                },
                status=status.HTTP_403_FORBIDDEN,
            )
        return None

    def _payload_response(self, request):
        err = self._check_platform_admin(request)
        if err is not None:
            return err
        payload = build_bootstrap_payload(request.user, request=request)
        return Response({"ok": True, "payload": payload})


# ---------------------------------------------------------------------------
# Tenants
# ---------------------------------------------------------------------------


class PlatformTenantsCreateView(PlatformAdminMixin, APIView):
    """POST /api/platform/tenants/ — create tenant."""

    def post(self, request):
        err = self._check_platform_admin(request)
        if err is not None:
            return err
        data = request.data or {}
        name = (data.get("name") or "").strip()
        slug = (data.get("slug") or data.get("schemaName") or "").strip().lower()
        schema_name = (data.get("schemaName") or slug or "").strip().lower()
        primary_domain = (data.get("primaryDomain") or "").strip()
        is_active = data.get("isActive", True)
        if not name:
            return Response(
                {"ok": False, "error": {"message": "name is required", "code": "validation"}},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if not schema_name:
            return Response(
                {"ok": False, "error": {"message": "schemaName/slug is required", "code": "validation"}},
                status=status.HTTP_400_BAD_REQUEST,
            )
        subdomain = (primary_domain.split(".")[0] if primary_domain else schema_name)
        if subdomain:
            try:
                validate_subdomain_rfc(subdomain)
            except ValueError as e:
                return Response(
                    {"ok": False, "error": {"message": str(e), "code": "validation"}},
                    status=status.HTTP_400_BAD_REQUEST,
                )
        def do_create():
            tenant, _ = Tenant.objects.get_or_create(
                schema_name=schema_name,
                defaults={
                    "nombre": name,
                    "domain": primary_domain.split(".", 1)[-1] if "." in primary_domain else "localhost",
                    "subdomain": subdomain or schema_name,
                    "enabled": is_active,
                },
            )
            if tenant.nombre != name or tenant.enabled != is_active:
                tenant.nombre = name
                tenant.enabled = is_active
                tenant.save(update_fields=["nombre", "enabled"])
            primary = getattr(tenant, "primary_domain", None) or ""
            if primary:
                TenantDomain.objects.get_or_create(
                    domain=primary,
                    defaults={"tenant": tenant, "is_primary": True},
                )
            return tenant

        try:
            if tenants_enabled():
                with tenant_schema_context(public_schema_name()):
                    do_create()
            else:
                do_create()
        except Exception as e:
            return Response(
                {"ok": False, "error": {"message": str(e), "code": "create_failed"}},
                status=status.HTTP_400_BAD_REQUEST,
            )
        payload = build_bootstrap_payload(request.user)
        return Response({"ok": True, "payload": payload})


class PlatformTenantsDeleteView(PlatformAdminMixin, APIView):
    """POST /api/platform/tenants/delete/ — delete tenant by id or slug."""

    def post(self, request):
        err = self._check_platform_admin(request)
        if err is not None:
            return err
        data = request.data or {}
        tenant_id = data.get("id")
        slug = (data.get("slug") or "").strip().lower()
        if not tenant_id and not slug:
            return Response(
                {"ok": False, "error": {"message": "id or slug is required", "code": "validation"}},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            if tenants_enabled():
                with tenant_schema_context(public_schema_name()):
                    if slug:
                        tenant = Tenant.objects.get(schema_name=slug)
                    else:
                        tenant = Tenant.objects.get(pk=tenant_id)
                    schema_name = tenant.schema_name
            else:
                if slug:
                    tenant = Tenant.objects.get(schema_name=slug)
                else:
                    tenant = Tenant.objects.get(pk=tenant_id)
                schema_name = tenant.schema_name
            call_command("remove_tenant", schema_name=schema_name, noinput=True)
        except Tenant.DoesNotExist:
            return Response(
                {"ok": False, "error": {"message": "Tenant not found.", "code": "not_found"}},
                status=status.HTTP_404_NOT_FOUND,
            )
        except Exception as e:
            return Response(
                {"ok": False, "error": {"message": str(e), "code": "delete_failed"}},
                status=status.HTTP_400_BAD_REQUEST,
            )
        payload = build_bootstrap_payload(request.user)
        return Response({"ok": True, "payload": payload})


# ---------------------------------------------------------------------------
# Users
# ---------------------------------------------------------------------------


class PlatformUsersSaveView(PlatformAdminMixin, APIView):
    """POST /api/platform/users/ — create or update platform user."""

    def post(self, request):
        err = self._check_platform_admin(request)
        if err is not None:
            return err
        data = request.data or {}
        user_id = data.get("id")
        email = (data.get("email") or "").strip().lower()
        display_name = (data.get("displayName") or "").strip()
        password = data.get("password")
        is_platform_admin = data.get("isPlatformAdmin", False)
        is_active = data.get("isActive", True)
        tenant_memberships = data.get("tenantMemberships") or []
        if not email:
            return Response(
                {"ok": False, "error": {"message": "email is required", "code": "validation"}},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if not user_id and not tenant_memberships:
            return Response(
                {"ok": False, "error": {"message": "At least one tenant membership required for new user", "code": "validation"}},
                status=status.HTTP_400_BAD_REQUEST,
            )
        tenant_slug = (tenant_memberships[0].get("tenantSlug") or "").strip() if tenant_memberships else None
        tenant = None
        if tenant_slug:
            if tenants_enabled():
                with tenant_schema_context(public_schema_name()):
                    tenant = Tenant.objects.filter(schema_name=tenant_slug).first()
            else:
                tenant = Tenant.objects.filter(schema_name=tenant_slug).first()
            if not tenant:
                return Response(
                    {"ok": False, "error": {"message": f"Tenant '{tenant_slug}' not found", "code": "validation"}},
                    status=status.HTTP_400_BAD_REQUEST,
                )
        try:
            if tenants_enabled():
                with tenant_schema_context(public_schema_name()):
                    user = self._save_user(user_id, email, display_name, password, is_platform_admin, is_active, tenant)
            else:
                user = self._save_user(user_id, email, display_name, password, is_platform_admin, is_active, tenant)
        except Exception as e:
            return Response(
                {"ok": False, "error": {"message": str(e), "code": "save_failed"}},
                status=status.HTTP_400_BAD_REQUEST,
            )
        payload = build_bootstrap_payload(request.user)
        return Response({"ok": True, "payload": payload})

    def _save_user(self, user_id, email, display_name, password, is_platform_admin, is_active, tenant):
        from django.contrib.auth.models import Group
        parts = (display_name or "").strip().split(None, 1)
        first_name = parts[0] if parts else ""
        last_name = parts[1] if len(parts) > 1 else ""
        username = email or (f"user_{user_id}" if user_id else "user")
        if user_id:
            user = UserModel.objects.get(pk=user_id)
            user.email = email
            user.username = username
            user.first_name = first_name
            user.last_name = last_name
            user.is_staff = is_platform_admin
            user.is_superuser = is_platform_admin
            user.is_active = is_active
            if tenant is not None:
                user.tenant = tenant
            if password:
                user.set_password(password)
            user.save()
            # Sync role group
            role_group, _ = Group.objects.get_or_create(name="platform_admin")
            if is_platform_admin:
                user.groups.add(role_group)
            else:
                user.groups.remove(role_group)
            return user
        if not password:
            raise ValueError("Password is required for new user")
        user = UserModel.objects.create_user(
            email=email,
            username=username,
            password=password,
            first_name=first_name,
            last_name=last_name,
            is_staff=is_platform_admin,
            is_superuser=is_platform_admin,
            is_active=is_active,
            tenant=tenant,
        )
        if is_platform_admin:
            role_group, _ = Group.objects.get_or_create(name="platform_admin")
            user.groups.add(role_group)
        return user


class PlatformUsersDeleteView(PlatformAdminMixin, APIView):
    """POST /api/platform/users/delete/ — delete user by id or email."""

    def post(self, request):
        err = self._check_platform_admin(request)
        if err is not None:
            return err
        data = request.data or {}
        user_id = data.get("id")
        email = (data.get("email") or "").strip().lower()
        if not user_id and not email:
            return Response(
                {"ok": False, "error": {"message": "id or email is required", "code": "validation"}},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            if tenants_enabled():
                with tenant_schema_context(public_schema_name()):
                    if user_id:
                        user = UserModel.objects.get(pk=user_id)
                    else:
                        user = UserModel.objects.get(email=email)
                    user.delete()
            else:
                if user_id:
                    user = UserModel.objects.get(pk=user_id)
                else:
                    user = UserModel.objects.get(email=email)
                user.delete()
        except UserModel.DoesNotExist:
            return Response(
                {"ok": False, "error": {"message": "User not found.", "code": "not_found"}},
                status=status.HTTP_404_NOT_FOUND,
            )
        payload = build_bootstrap_payload(request.user)
        return Response({"ok": True, "payload": payload})


# ---------------------------------------------------------------------------
# Integrations
# ---------------------------------------------------------------------------


class PlatformIntegrationsSaveView(PlatformAdminMixin, APIView):
    """POST /api/platform/integrations/ — create or update integration definition."""

    def post(self, request):
        err = self._check_platform_admin(request)
        if err is not None:
            return err
        data = request.data or {}
        key = (data.get("key") or "").strip()
        if not key:
            return Response(
                {"ok": False, "error": {"message": "key is required", "code": "validation"}},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            if tenants_enabled():
                with tenant_schema_context(public_schema_name()):
                    obj, _ = IntegrationDefinition.objects.update_or_create(
                        key=key,
                        defaults={
                            "name": (data.get("name") or key),
                            "category": (data.get("category") or ""),
                            "base_url": (data.get("baseUrl") or ""),
                            "openapi_url": (data.get("openapiUrl") or ""),
                            "default_auth_type": (data.get("defaultAuthType") or "bearer"),
                            "auth_scope": (data.get("authScope") or "tenant"),
                            "auth_config_schema": data.get("authConfigSchema") or {},
                            "global_auth_config": data.get("globalAuthConfig") or {},
                            "assistant_docs_markdown": (data.get("assistantDocsMarkdown") or ""),
                            "default_headers": data.get("defaultHeaders") or {},
                            "is_active": data.get("isActive", True),
                        },
                    )
            else:
                obj, _ = IntegrationDefinition.objects.update_or_create(
                    key=key,
                    defaults={
                        "name": (data.get("name") or key),
                        "category": (data.get("category") or ""),
                        "base_url": (data.get("baseUrl") or ""),
                        "openapi_url": (data.get("openapiUrl") or ""),
                        "default_auth_type": (data.get("defaultAuthType") or "bearer"),
                        "auth_scope": (data.get("authScope") or "tenant"),
                        "auth_config_schema": data.get("authConfigSchema") or {},
                        "global_auth_config": data.get("globalAuthConfig") or {},
                        "assistant_docs_markdown": (data.get("assistantDocsMarkdown") or ""),
                        "default_headers": data.get("defaultHeaders") or {},
                        "is_active": data.get("isActive", True),
                    },
                )
        except Exception as e:
            return Response(
                {"ok": False, "error": {"message": str(e), "code": "save_failed"}},
                status=status.HTTP_400_BAD_REQUEST,
            )
        payload = build_bootstrap_payload(request.user)
        return Response({"ok": True, "payload": payload})


class PlatformIntegrationsDeleteView(PlatformAdminMixin, APIView):
    """POST /api/platform/integrations/delete/ — delete integration by key."""

    def post(self, request):
        err = self._check_platform_admin(request)
        if err is not None:
            return err
        data = request.data or {}
        key = (data.get("key") or "").strip()
        if not key:
            return Response(
                {"ok": False, "error": {"message": "key is required", "code": "validation"}},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            if tenants_enabled():
                with tenant_schema_context(public_schema_name()):
                    IntegrationDefinition.objects.filter(key=key).delete()
            else:
                IntegrationDefinition.objects.filter(key=key).delete()
        except Exception as e:
            return Response(
                {"ok": False, "error": {"message": str(e), "code": "delete_failed"}},
                status=status.HTTP_400_BAD_REQUEST,
            )
        payload = build_bootstrap_payload(request.user)
        return Response({"ok": True, "payload": payload})


# ---------------------------------------------------------------------------
# Tenant integrations
# ---------------------------------------------------------------------------


class PlatformTenantIntegrationsSaveView(PlatformAdminMixin, APIView):
    """POST /api/platform/tenant-integrations/ — create or update tenant integration."""

    def post(self, request):
        err = self._check_platform_admin(request)
        if err is not None:
            return err
        data = request.data or {}
        tenant_slug = (data.get("tenantSlug") or "").strip()
        integration_key = (data.get("integrationKey") or "").strip()
        if not tenant_slug or not integration_key:
            return Response(
                {"ok": False, "error": {"message": "tenantSlug and integrationKey are required", "code": "validation"}},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            if tenants_enabled():
                with tenant_schema_context(public_schema_name()):
                    tenant = Tenant.objects.get(schema_name=tenant_slug)
                    integration = IntegrationDefinition.objects.get(key=integration_key)
                    ti, _ = TenantIntegration.objects.update_or_create(
                        tenant=tenant,
                        integration=integration,
                        defaults={
                            "is_enabled": data.get("isEnabled", True),
                            "notes": (data.get("notes") or ""),
                            "assistant_docs_override": (data.get("assistantDocsOverride") or ""),
                            "tenant_auth_config": data.get("tenantAuthConfig") or {},
                        },
                    )
            else:
                tenant = Tenant.objects.get(schema_name=tenant_slug)
                integration = IntegrationDefinition.objects.get(key=integration_key)
                ti, _ = TenantIntegration.objects.update_or_create(
                    tenant=tenant,
                    integration=integration,
                    defaults={
                        "is_enabled": data.get("isEnabled", True),
                        "notes": (data.get("notes") or ""),
                        "assistant_docs_override": (data.get("assistantDocsOverride") or ""),
                        "tenant_auth_config": data.get("tenantAuthConfig") or {},
                    },
                )
        except Tenant.DoesNotExist:
            return Response(
                {"ok": False, "error": {"message": "Tenant not found.", "code": "not_found"}},
                status=status.HTTP_404_NOT_FOUND,
            )
        except IntegrationDefinition.DoesNotExist:
            return Response(
                {"ok": False, "error": {"message": "Integration not found.", "code": "not_found"}},
                status=status.HTTP_404_NOT_FOUND,
            )
        payload = build_bootstrap_payload(request.user)
        return Response({"ok": True, "payload": payload})


# ---------------------------------------------------------------------------
# Platform configuration (site, OAuth, WhatsApp, Shopify, etc.)
# ---------------------------------------------------------------------------

_CAMEL_TO_ATTR = {
    "siteName": "site_name",
    "company": "company",
    "myUrl": "my_url",
    "whatsappWebhookToken": "whatsapp_webhook_token",
    "whatsappWebhookRedirect": "whatsapp_webhook_redirect",
    "fbSystemToken": "fb_system_token",
    "fbMoioBotAppId": "fb_moio_bot_app_id",
    "fbMoioBusinessManagerId": "fb_moio_business_manager_id",
    "fbMoioBotAppSecret": "fb_moio_bot_app_secret",
    "fbMoioBotConfigurationId": "fb_moio_bot_configuration_id",
    "googleOauthClientId": "google_oauth_client_id",
    "googleOauthClientSecret": "google_oauth_client_secret",
    "microsoftOauthClientId": "microsoft_oauth_client_id",
    "microsoftOauthClientSecret": "microsoft_oauth_client_secret",
    "shopifyClientId": "shopify_client_id",
    "shopifyClientSecret": "shopify_client_secret",
}


class PlatformConfigurationSaveView(PlatformAdminMixin, APIView):
    """POST /api/platform/configuration/ — save platform configuration (singleton)."""

    def post(self, request):
        err = self._check_platform_admin(request)
        if err is not None:
            return err
        data = request.data or {}

        def do_save():
            cfg = PlatformConfiguration.objects.first()
            if cfg is None:
                cfg = PlatformConfiguration()
            for camel, attr in _CAMEL_TO_ATTR.items():
                if camel in data:
                    val = data[camel]
                    setattr(cfg, attr, (str(val).strip() if val is not None else ""))
            cfg.save()
            return build_bootstrap_payload(request.user, request=request)

        if tenants_enabled():
            with tenant_schema_context(public_schema_name()):
                payload = do_save()
        else:
            payload = do_save()
        return Response({"ok": True, "payload": payload})


# ---------------------------------------------------------------------------
# Notifications (persisted; shared platform-wide via main bootstrap)
# ---------------------------------------------------------------------------

_NOTIFICATION_CAMEL_TO_ATTR = {
    "title": "title",
    "iconUrl": "icon_url",
    "badgeUrl": "badge_url",
    "requireInteraction": "require_interaction",
    "renotify": "renotify",
    "silent": "silent",
    "testTitle": "test_title",
    "testBody": "test_body",
}


class PlatformNotificationsSaveView(PlatformAdminMixin, APIView):
    """POST /api/platform/notifications/ — save notification settings (persisted)."""

    def post(self, request):
        err = self._check_platform_admin(request)
        if err is not None:
            return err
        data = (request.data or {}).get("settings") or request.data or {}

        def do_save():
            obj = PlatformNotificationSettings.objects.first()
            if obj is None:
                obj = PlatformNotificationSettings()
            for camel, attr in _NOTIFICATION_CAMEL_TO_ATTR.items():
                if camel in data:
                    val = data[camel]
                    if attr in ("require_interaction", "renotify", "silent"):
                        setattr(obj, attr, bool(val))
                    else:
                        setattr(obj, attr, (str(val).strip() if val is not None else ""))
            obj.save()
            return build_bootstrap_payload(request.user, request=request)

        if tenants_enabled():
            with tenant_schema_context(public_schema_name()):
                payload = do_save()
        else:
            payload = do_save()
        return Response({"ok": True, "payload": payload})


# ---------------------------------------------------------------------------
# Global skills (stub)
# ---------------------------------------------------------------------------


class PlatformSkillsSaveView(PlatformAdminMixin, APIView):
    """POST /api/platform/skills/ — stub: return current bootstrap."""

    def post(self, request):
        payload = build_bootstrap_payload(request.user, request=request)
        return Response({"ok": True, "payload": payload})


class PlatformSkillsDeleteView(PlatformAdminMixin, APIView):
    """POST /api/platform/skills/delete/ — stub: return current bootstrap."""

    def post(self, request):
        payload = build_bootstrap_payload(request.user, request=request)
        return Response({"ok": True, "payload": payload})


# ---------------------------------------------------------------------------
# Plugins (stub)
# ---------------------------------------------------------------------------


class PlatformPluginsView(PlatformAdminMixin, APIView):
    """GET /api/platform/plugins/?tenant=... and POST /api/platform/plugins/ — stub: return empty PluginAdminState."""

    def get(self, request):
        err = self._check_platform_admin(request)
        if err is not None:
            return err
        payload = {
            "sync": {"syncedCount": 0, "invalid": []},
            "plugins": [],
            "tenantPlugins": [],
            "tenantPluginAssignments": [],
        }
        return Response({"ok": True, "payload": payload})

    def post(self, request):
        err = self._check_platform_admin(request)
        if err is not None:
            return err
        payload = {
            "sync": {"syncedCount": 0, "invalid": []},
            "plugins": [],
            "tenantPlugins": [],
            "tenantPluginAssignments": [],
        }
        return Response({"ok": True, "payload": payload})
