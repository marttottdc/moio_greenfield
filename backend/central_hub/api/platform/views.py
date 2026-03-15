"""
Platform Admin API views: POST/delete for tenants, users, integrations, etc.
All require is_staff or is_superuser and return { "ok": true, "payload": BootstrapPayload }.
"""
from __future__ import annotations

import base64
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.db.models import Q
from django.utils import timezone
from rest_framework import status
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.authentication import JWTAuthentication

from central_hub.api.platform_bootstrap import build_bootstrap_payload, _is_platform_admin_user
from central_hub.api.platform.plugin_admin_state import platform_plugin_admin_state
from central_hub.authentication import TenantJWTAAuthentication
from central_hub.models import (
    Capability,
    Plan,
    PlatformAdminKpiSnapshot,
    PlatformConfiguration,
    PlatformNotificationSettings,
    Role,
)
from agent_console.models import AgentConsoleInstalledPlugin
from agent_console.services.runtime_service import invalidate_runtime_backend_cache
from agent_console.services.plugin_installation_service import parse_plugin_bundle_zip
from moio_platform.authentication import BearerTokenAuthentication
from tenancy.models import IntegrationDefinition, Tenant, TenantDomain, TenantIntegration
from tenancy.tenant_support import public_schema_name, tenant_rls_context, tenants_enabled
from tenancy.validators import validate_subdomain_rfc

UserModel = get_user_model()

MODULE_ENABLEMENT_DEFAULTS = {
    "crm": True,
    "flowsDatalab": False,
    "chatbot": False,
    "agentConsole": False,
}


def _is_known_plan_key(plan_key: str) -> bool:
    key = (plan_key or "").strip().lower()
    if not key:
        return False
    return Plan.objects.filter(key=key).exists()


def _normalize_module_enablements(raw: object) -> dict:
    normalized = dict(MODULE_ENABLEMENT_DEFAULTS)
    if not isinstance(raw, dict):
        return normalized
    for key in MODULE_ENABLEMENT_DEFAULTS:
        if key in raw:
            normalized[key] = bool(raw.get(key))
    # CRM is the base module and should always remain enabled.
    normalized["crm"] = True
    return normalized


def _apply_module_enablements_to_tenant(tenant: Tenant, raw: object) -> None:
    """
    Persist module enablements in both tenant.features and tenant.ui.

    Frontend/admin reads moduleEnablements from Platform Bootstrap.
    Runtime capability checks can use feature flags directly.
    """
    module_enablements = _normalize_module_enablements(raw)
    features = dict(getattr(tenant, "features", None) or {})
    features["crm"] = True
    features["flows"] = bool(module_enablements["flowsDatalab"])
    features["datalab"] = bool(module_enablements["flowsDatalab"])
    features["chatbot"] = bool(module_enablements["chatbot"])
    features["agent_console"] = bool(module_enablements["agentConsole"])

    ui = dict(getattr(tenant, "ui", None) or {})
    ui["module_enablements"] = module_enablements

    tenant.features = features
    tenant.ui = ui
    tenant.save(update_fields=["features", "ui"])


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


def _parse_period(period: str | None):
    """Return (start_dt, end_dt) for the period. end_dt=now, start_dt=now-delta. None means no filter."""
    if not (period or str(period).strip()):
        return None, None
    now = timezone.now()
    period = str(period).strip().lower()
    if period in ("24h", "1d", "1day"):
        return now - timedelta(hours=24), now
    if period in ("7d", "7day", "7days", "1w"):
        return now - timedelta(days=7), now
    if period in ("30d", "30day", "30days", "1m"):
        return now - timedelta(days=30), now
    return None, None


# KPIs are always served from PlatformAdminKpiSnapshot, filled by Celery (refresh_platform_admin_kpi_snapshots).


def _kpi_period_to_key(period: str | None) -> str:
    """Normalize period query param to snapshot period_key."""
    if not (period or "").strip():
        return "all"
    p = (period or "").strip().lower()
    if p in ("24h", "1d", "1day"):
        return "24h"
    if p in ("7d", "7day", "7days", "1w"):
        return "7d"
    if p in ("30d", "30day", "30days", "1m"):
        return "30d"
    return "all"


# Max age (seconds) for snapshot to be considered fresh; older triggers a Celery refresh.
PLATFORM_KPI_CACHE_MAX_AGE_SECONDS = 600  # 10 minutes


def _get_kpi_snapshot(period_key: str, tenant_slug: str | None) -> PlatformAdminKpiSnapshot | None:
    """Return the latest snapshot for this period and tenant (all vs single)."""
    if tenant_slug:
        tenant_id = Tenant.objects.filter(enabled=True).filter(
            Q(schema_name=tenant_slug) | Q(subdomain=tenant_slug)
        ).values_list("id", flat=True).first()
        if tenant_id is None:
            return None
        return (
            PlatformAdminKpiSnapshot.objects.filter(
                period_key=period_key,
                tenant_id=tenant_id,
            )
            .order_by("-updated_at")
            .first()
        )
    return (
        PlatformAdminKpiSnapshot.objects.filter(
            period_key=period_key,
            tenant_id__isnull=True,
        )
        .order_by("-updated_at")
        .first()
    )


def _snapshot_to_payload(snapshot: PlatformAdminKpiSnapshot | None, period: str | None, tenant_slug: str | None):
    """Build API payload from snapshot or zeros if None."""
    if snapshot is None:
        return {
            "contacts": 0,
            "accounts": 0,
            "deals": 0,
            "activities": 0,
            "flow_executions": 0,
            "agent_sessions": 0,
            "total_activity_per_hour": None,
            "period": period or "all",
            "tenant": tenant_slug or "all",
            "from_cache": False,
            "cached_at": None,
        }
    return {
        "contacts": snapshot.contacts,
        "accounts": snapshot.accounts,
        "deals": snapshot.deals,
        "activities": snapshot.activities,
        "flow_executions": snapshot.flow_executions,
        "agent_sessions": snapshot.agent_sessions,
        "total_activity_per_hour": snapshot.total_activity_per_hour,
        "period": period or "all",
        "tenant": tenant_slug or "all",
        "from_cache": True,
        "cached_at": snapshot.updated_at.isoformat(),
    }


class PlatformAdminKPIsView(PlatformAdminMixin, APIView):
    """
    GET /api/platform/kpis/ — platform admin KPIs. Always served from snapshot (Celery).
    Query params: tenant (optional slug, omit for all), period (optional: 24h, 7d, 30d).
    Data is filled by refresh_platform_admin_kpi_snapshots (run on Beat or when triggered).
    If snapshot is missing or stale, we trigger the task and return current data (or zeros).
    """

    def get(self, request):
        err = self._check_platform_admin(request)
        if err is not None:
            return err
        tenant_slug = (request.query_params.get("tenant") or "").strip() or None
        period = (request.query_params.get("period") or "").strip() or None
        period_key = _kpi_period_to_key(period)
        from django.utils import timezone

        snapshot = _get_kpi_snapshot(period_key, tenant_slug)
        now = timezone.now()
        age_seconds = (now - snapshot.updated_at).total_seconds() if snapshot else float("inf")  # no snapshot = stale
        if snapshot is None or age_seconds > PLATFORM_KPI_CACHE_MAX_AGE_SECONDS:
            try:
                from central_hub.tasks import refresh_platform_admin_kpi_snapshots
                from central_hub.api.platform.kpi_aggregation import get_enabled_tenants_for_kpis
                tenant_list = get_enabled_tenants_for_kpis(tenant_slug)
                tenant_slugs = [s for _, s in tenant_list] if tenant_list else None
                refresh_platform_admin_kpi_snapshots.delay(
                    period_keys=[period_key],
                    tenant_slug=tenant_slug,
                    tenant_slugs=tenant_slugs,
                )
            except Exception:
                pass
        payload = _snapshot_to_payload(snapshot, period, tenant_slug)
        return Response({"ok": True, "payload": payload})


class PlatformAdminKPIsRefreshView(PlatformAdminMixin, APIView):
    """
    POST /api/platform/kpis/refresh/ — enqueue Celery task to refresh KPIs.
    Query/body: tenant (optional slug), period (optional: 24h, 7d, 30d).
    Returns { "ok": true, "payload": { "task_id": "<id>" } }.
    """

    def post(self, request):
        err = self._check_platform_admin(request)
        if err is not None:
            return err
        data = getattr(request, "data", None) or {}
        tenant_slug = (
            (request.query_params.get("tenant") or "").strip()
            or (data.get("tenant") or "").strip()
            or None
        )
        period = (
            (request.query_params.get("period") or "").strip()
            or (data.get("period") or "").strip()
            or None
        )
        # Client may send tenant_slugs (list) so the task does not discover tenants in the worker
        raw_slugs = data.get("tenant_slugs")
        if isinstance(raw_slugs, list):
            tenant_slugs = [str(s).strip() for s in raw_slugs if (s or "").strip()]
        else:
            tenant_slugs = None
        if tenant_slugs is None:
            from central_hub.api.platform.kpi_aggregation import get_enabled_tenants_for_kpis
            tenant_list = get_enabled_tenants_for_kpis(tenant_slug)
            tenant_slugs = [s for _, s in tenant_list] if tenant_list else None
        period_key = _kpi_period_to_key(period)
        try:
            from central_hub.tasks import refresh_platform_admin_kpi_snapshots

            result = refresh_platform_admin_kpi_snapshots.delay(
                period_keys=[period_key],
                tenant_slug=tenant_slug,
                tenant_slugs=tenant_slugs,
            )
            return Response(
                {"ok": True, "payload": {"task_id": result.id}},
                status=status.HTTP_200_OK,
            )
        except Exception as e:
            return Response(
                {
                    "ok": False,
                    "error": {
                        "message": f"Failed to enqueue KPI refresh: {e}",
                        "code": "celery_unavailable",
                    },
                },
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )


class PlatformAdminKPIsRefreshStatusView(PlatformAdminMixin, APIView):
    """
    GET /api/platform/kpis/refresh/status/?task_id=xxx&tenant=&period=
    Returns { "ok": true, "payload": { "status": "PENDING"|"SUCCESS"|"FAILURE", "kpis"?: {...}, "error"?: str } }.
    """

    def get(self, request):
        err = self._check_platform_admin(request)
        if err is not None:
            return err
        task_id = (request.query_params.get("task_id") or "").strip()
        if not task_id:
            return Response(
                {"ok": False, "error": {"message": "task_id is required", "code": "validation"}},
                status=status.HTTP_400_BAD_REQUEST,
            )
        tenant_slug = (request.query_params.get("tenant") or "").strip() or None
        period = (request.query_params.get("period") or "").strip() or None
        period_key = _kpi_period_to_key(period)

        from celery.result import AsyncResult

        ar = AsyncResult(task_id)
        if not ar.ready():
            return Response(
                {"ok": True, "payload": {"status": "PENDING"}},
                status=status.HTTP_200_OK,
            )
        if ar.successful():
            snapshot = _get_kpi_snapshot(period_key, tenant_slug)
            kpis = _snapshot_to_payload(snapshot, period, tenant_slug)
            return Response(
                {"ok": True, "payload": {"status": "SUCCESS", "kpis": kpis}},
                status=status.HTTP_200_OK,
            )
        return Response(
            {
                "ok": True,
                "payload": {
                    "status": "FAILURE",
                    "error": str(ar.result) if ar.result is not None else "Unknown error",
                },
            },
            status=status.HTTP_200_OK,
        )


# ---------------------------------------------------------------------------
# Plans
# ---------------------------------------------------------------------------


class PlatformPlansSaveView(PlatformAdminMixin, APIView):
    """POST /api/platform/plans/ — create or update plan."""

    def post(self, request):
        err = self._check_platform_admin(request)
        if err is not None:
            return err
        data = request.data or {}
        plan_id = data.get("id")
        key = (data.get("key") or "").strip().lower()
        name = (data.get("name") or "").strip()
        display_order = data.get("displayOrder")
        is_active = data.get("isActive") if data.get("isActive") is not None else True
        is_self_provision_default = bool(data.get("isSelfProvisionDefault")) if data.get("isSelfProvisionDefault") is not None else False
        pricing_policy = data.get("pricingPolicy")
        entitlement_policy = data.get("entitlementPolicy")

        if not key:
            return Response(
                {"ok": False, "error": {"message": "key is required", "code": "validation"}},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if not name:
            return Response(
                {"ok": False, "error": {"message": "name is required", "code": "validation"}},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if not key.replace("_", "").isalnum():
            return Response(
                {"ok": False, "error": {"message": "key must be alphanumeric (and underscores)", "code": "validation"}},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if pricing_policy is not None and not isinstance(pricing_policy, dict):
            return Response(
                {"ok": False, "error": {"message": "pricingPolicy must be an object", "code": "validation"}},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if entitlement_policy is not None and not isinstance(entitlement_policy, dict):
            return Response(
                {"ok": False, "error": {"message": "entitlementPolicy must be an object", "code": "validation"}},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            if plan_id:
                plan = Plan.objects.get(pk=plan_id)
                plan.key = key
                plan.name = name
                if display_order is not None:
                    plan.display_order = display_order
                plan.is_active = bool(is_active)
                plan.is_self_provision_default = is_self_provision_default
                if pricing_policy is not None:
                    plan.pricing_policy = pricing_policy
                if entitlement_policy is not None:
                    plan.entitlement_policy = entitlement_policy
                if plan.is_self_provision_default:
                    Plan.objects.exclude(pk=plan.pk).filter(is_self_provision_default=True).update(is_self_provision_default=False)
                plan.save()
            else:
                plan, _ = Plan.objects.update_or_create(
                    key=key,
                    defaults={
                        "name": name,
                        "display_order": display_order if display_order is not None else 0,
                        "is_active": bool(is_active),
                        "is_self_provision_default": is_self_provision_default,
                        "pricing_policy": pricing_policy if isinstance(pricing_policy, dict) else {},
                        "entitlement_policy": entitlement_policy if isinstance(entitlement_policy, dict) else {},
                    },
                )
                if is_self_provision_default:
                    Plan.objects.exclude(pk=plan.pk).filter(is_self_provision_default=True).update(is_self_provision_default=False)
        except Plan.DoesNotExist:
            return Response(
                {"ok": False, "error": {"message": "Plan not found.", "code": "not_found"}},
                status=status.HTTP_404_NOT_FOUND,
            )
        payload = build_bootstrap_payload(request.user)
        return Response({"ok": True, "payload": payload})


class PlatformPlansDeleteView(PlatformAdminMixin, APIView):
    """POST /api/platform/plans/delete/ — delete plan by id or key."""

    def post(self, request):
        err = self._check_platform_admin(request)
        if err is not None:
            return err
        data = request.data or {}
        plan_id = data.get("id")
        key = (data.get("key") or "").strip().lower()
        if not plan_id and not key:
            return Response(
                {"ok": False, "error": {"message": "id or key is required", "code": "validation"}},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            if key:
                plan = Plan.objects.get(key=key)
            else:
                plan = Plan.objects.get(pk=plan_id)
            plan.delete()
        except Plan.DoesNotExist:
            return Response(
                {"ok": False, "error": {"message": "Plan not found.", "code": "not_found"}},
                status=status.HTTP_404_NOT_FOUND,
            )
        payload = build_bootstrap_payload(request.user)
        return Response({"ok": True, "payload": payload})


# ---------------------------------------------------------------------------
# Roles (combinations of capabilities; slug = Django Group name for assignment)
# ---------------------------------------------------------------------------


class PlatformRolesSaveView(PlatformAdminMixin, APIView):
    """POST /api/platform/roles/ — create or update role."""

    def post(self, request):
        err = self._check_platform_admin(request)
        if err is not None:
            return err
        data = request.data or {}
        role_id = data.get("id")
        name = (data.get("name") or "").strip()
        slug = (data.get("slug") or "").strip().lower().replace(" ", "_")
        display_order = data.get("displayOrder")
        capability_keys = data.get("capabilityKeys")
        if isinstance(capability_keys, list):
            capability_keys = [str(k).strip() for k in capability_keys if k]
        else:
            capability_keys = []

        if not name:
            return Response(
                {"ok": False, "error": {"message": "name is required", "code": "validation"}},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if not slug:
            return Response(
                {"ok": False, "error": {"message": "slug is required", "code": "validation"}},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if not slug.replace("_", "").isalnum():
            return Response(
                {"ok": False, "error": {"message": "slug must be alphanumeric (and underscores)", "code": "validation"}},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            if role_id:
                role = Role.objects.get(pk=role_id)
                role.name = name
                role.slug = slug
                if display_order is not None:
                    role.display_order = display_order
                role.save()
            else:
                role, _ = Role.objects.update_or_create(
                    slug=slug,
                    defaults={
                        "name": name,
                        "display_order": display_order if display_order is not None else 0,
                    },
                )
            caps = list(Capability.objects.filter(key__in=capability_keys))
            role.capabilities.set(caps)
        except Role.DoesNotExist:
            return Response(
                {"ok": False, "error": {"message": "Role not found.", "code": "not_found"}},
                status=status.HTTP_404_NOT_FOUND,
            )
        payload = build_bootstrap_payload(request.user)
        return Response({"ok": True, "payload": payload})


class PlatformRolesDeleteView(PlatformAdminMixin, APIView):
    """POST /api/platform/roles/delete/ — delete role by id or slug."""

    def post(self, request):
        err = self._check_platform_admin(request)
        if err is not None:
            return err
        data = request.data or {}
        role_id = data.get("id")
        slug = (data.get("slug") or "").strip().lower()
        if not role_id and not slug:
            return Response(
                {"ok": False, "error": {"message": "id or slug is required", "code": "validation"}},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            if slug:
                role = Role.objects.get(slug=slug)
            else:
                role = Role.objects.get(pk=role_id)
            role.delete()
        except Role.DoesNotExist:
            return Response(
                {"ok": False, "error": {"message": "Role not found.", "code": "not_found"}},
                status=status.HTTP_404_NOT_FOUND,
            )
        payload = build_bootstrap_payload(request.user)
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
        plan = (data.get("plan") or "").strip().lower()
        module_enablements = data.get("moduleEnablements")
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
        if not plan:
            return Response(
                {"ok": False, "error": {"message": "plan is required", "code": "validation"}},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if not _is_known_plan_key(plan):
            return Response(
                {"ok": False, "error": {"message": "Plan not found.", "code": "validation"}},
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
                    "plan": plan,
                },
            )
            if tenant.nombre != name or tenant.enabled != is_active or tenant.plan != plan:
                tenant.nombre = name
                tenant.enabled = is_active
                tenant.plan = plan
                tenant.save(update_fields=["nombre", "enabled", "plan"])
            primary = getattr(tenant, "primary_domain", None) or ""
            if primary:
                TenantDomain.objects.get_or_create(
                    domain=primary,
                    defaults={"tenant": tenant, "is_primary": True},
                )
            if module_enablements is not None:
                _apply_module_enablements_to_tenant(tenant, module_enablements)
            return tenant

        try:
            if tenants_enabled():
                with tenant_rls_context(public_schema_name()):
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


class PlatformTenantsUpdateView(PlatformAdminMixin, APIView):
    """POST /api/platform/tenants/update/ — update tenant plan and optionally name, isActive."""

    def post(self, request):
        err = self._check_platform_admin(request)
        if err is not None:
            return err
        data = request.data or {}
        tenant_id = data.get("id")
        slug = (data.get("slug") or "").strip().lower()
        plan = (data.get("plan") or "").strip().lower()
        name = (data.get("name") or "").strip()
        is_active = data.get("isActive") if data.get("isActive") is not None else None
        module_enablements = data.get("moduleEnablements")

        if not tenant_id and not slug:
            return Response(
                {"ok": False, "error": {"message": "id or slug is required", "code": "validation"}},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if plan and not _is_known_plan_key(plan):
            return Response(
                {"ok": False, "error": {"message": "plan key is not recognized", "code": "validation"}},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            if tenants_enabled():
                with tenant_rls_context(public_schema_name()):
                    if slug:
                        tenant = Tenant.objects.get(schema_name=slug)
                    else:
                        tenant = Tenant.objects.get(pk=tenant_id)
            else:
                if slug:
                    tenant = Tenant.objects.get(schema_name=slug)
                else:
                    tenant = Tenant.objects.get(pk=tenant_id)

            update_fields = []
            if plan:
                tenant.plan = plan
                update_fields.append("plan")
            if name:
                tenant.nombre = name
                update_fields.append("nombre")
            if is_active is not None:
                tenant.enabled = bool(is_active)
                update_fields.append("enabled")
            if update_fields:
                tenant.save(update_fields=update_fields)
            if module_enablements is not None:
                _apply_module_enablements_to_tenant(tenant, module_enablements)
        except Tenant.DoesNotExist:
            return Response(
                {"ok": False, "error": {"message": "Tenant not found.", "code": "not_found"}},
                status=status.HTTP_404_NOT_FOUND,
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
                with tenant_rls_context(public_schema_name()):
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
                with tenant_rls_context(public_schema_name()):
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
                with tenant_rls_context(public_schema_name()):
                    user = self._save_user(
                        user_id, email, display_name, password, is_platform_admin, is_active, tenant, tenant_memberships
                    )
            else:
                user = self._save_user(
                    user_id, email, display_name, password, is_platform_admin, is_active, tenant, tenant_memberships
                )
        except Exception as e:
            return Response(
                {"ok": False, "error": {"message": str(e), "code": "save_failed"}},
                status=status.HTTP_400_BAD_REQUEST,
            )
        payload = build_bootstrap_payload(request.user)
        return Response({"ok": True, "payload": payload})

    def _save_user(self, user_id, email, display_name, password, is_platform_admin, is_active, tenant, tenant_memberships=None):
        from django.contrib.auth.models import Group
        tenant_memberships = tenant_memberships or []
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
            # Sync platform_admin group
            platform_admin_group, _ = Group.objects.get_or_create(name="platform_admin")
            if is_platform_admin:
                user.groups.add(platform_admin_group)
            else:
                user.groups.remove(platform_admin_group)
            # Sync tenant_admin group from membership role (admin = tenant_admin)
            tenant_admin_group, _ = Group.objects.get_or_create(name="tenant_admin")
            want_tenant_admin = any(
                (m.get("role") or "").strip().lower() == "admin"
                for m in tenant_memberships
            )
            if want_tenant_admin:
                user.groups.add(tenant_admin_group)
            else:
                user.groups.remove(tenant_admin_group)
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
        platform_admin_group, _ = Group.objects.get_or_create(name="platform_admin")
        if is_platform_admin:
            user.groups.add(platform_admin_group)
        tenant_admin_group, _ = Group.objects.get_or_create(name="tenant_admin")
        want_tenant_admin = any(
            (m.get("role") or "").strip().lower() == "admin"
            for m in tenant_memberships
        )
        if want_tenant_admin:
            user.groups.add(tenant_admin_group)
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
                with tenant_rls_context(public_schema_name()):
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
                with tenant_rls_context(public_schema_name()):
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
                with tenant_rls_context(public_schema_name()):
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
                with tenant_rls_context(public_schema_name()):
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
            with tenant_rls_context(public_schema_name()):
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
            with tenant_rls_context(public_schema_name()):
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
# Plugins
# ---------------------------------------------------------------------------


class PlatformPluginsView(PlatformAdminMixin, APIView):
    """GET/POST /api/platform/plugins/ — upload/list/approve plugin bundles."""
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    @staticmethod
    def _state_payload() -> dict:
        if tenants_enabled():
            with tenant_rls_context(public_schema_name()):
                return platform_plugin_admin_state()
        return platform_plugin_admin_state()

    def get(self, request):
        err = self._check_platform_admin(request)
        if err is not None:
            return err
        return Response({"ok": True, "payload": self._state_payload()})

    def post(self, request):
        err = self._check_platform_admin(request)
        if err is not None:
            return err

        data = request.data or {}
        bundle_file = request.FILES.get("bundle") or request.FILES.get("file")
        bundle_base64 = str(data.get("bundleBase64") or "").strip()
        bundle_bytes: bytes | None = None
        if bundle_file is None:
            candidate = data.get("bundle") or data.get("file")
            if hasattr(candidate, "read"):
                bundle_file = candidate
        if bundle_file is not None:
            bundle_bytes = bundle_file.read()
        elif bundle_base64:
            try:
                bundle_bytes = base64.b64decode(bundle_base64, validate=True)
            except Exception:
                return Response(
                    {"ok": False, "error": {"message": "bundleBase64 is not valid base64 data.", "code": "validation_error"}},
                    status=status.HTTP_400_BAD_REQUEST,
                )
        if bundle_bytes is not None:
            try:
                parsed = parse_plugin_bundle_zip(bundle_bytes)
            except Exception as exc:
                return Response(
                    {"ok": False, "error": {"message": f"Invalid plugin bundle: {exc}", "code": "validation_error"}},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            def _upsert() -> None:
                existing = AgentConsoleInstalledPlugin.objects.filter(plugin_id=parsed.plugin_id).first()
                is_platform_approved = existing.is_platform_approved if existing is not None else False
                AgentConsoleInstalledPlugin.objects.update_or_create(
                    plugin_id=parsed.plugin_id,
                    defaults={
                        "name": parsed.name,
                        "version": parsed.version,
                        "enabled": True,
                        "is_platform_approved": is_platform_approved,
                        "checksum_sha256": parsed.checksum_sha256,
                        "manifest": parsed.manifest,
                        "bundle_zip": parsed.bundle_zip,
                    },
                )

            if tenants_enabled():
                with tenant_rls_context(public_schema_name()):
                    _upsert()
            else:
                _upsert()
            invalidate_runtime_backend_cache()
            return Response({"ok": True, "payload": self._state_payload()})

        plugin_id = str(data.get("pluginId") or "").strip().lower()
        if not plugin_id:
            return Response(
                {
                    "ok": False,
                    "error": {
                        "message": "Missing plugin upload file ('bundle') or pluginId for approval update.",
                        "code": "validation_error",
                    },
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        is_platform_approved = bool(data.get("isPlatformApproved"))

        def _toggle_approval() -> bool:
            updated = AgentConsoleInstalledPlugin.objects.filter(plugin_id=plugin_id).update(
                is_platform_approved=is_platform_approved
            )
            return bool(updated)

        if tenants_enabled():
            with tenant_rls_context(public_schema_name()):
                updated = _toggle_approval()
        else:
            updated = _toggle_approval()
        if not updated:
            return Response(
                {"ok": False, "error": {"message": "Plugin not found.", "code": "not_found"}},
                status=status.HTTP_404_NOT_FOUND,
            )
        invalidate_runtime_backend_cache()
        return Response({"ok": True, "payload": self._state_payload()})
