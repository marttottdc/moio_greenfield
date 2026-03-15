"""Celery tasks for central_hub (e.g. async self-provision)."""
from __future__ import annotations

import logging

from celery import shared_task
from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.db import IntegrityError, transaction
from central_hub.integrations.shopify import tasks as _shopify_tasks  # noqa: F401,E402
from central_hub.models import ProvisioningJob, PlatformAdminKpiSnapshot, UserProfile
from tenancy.models import Tenant
from central_hub.plan_policy import get_self_provision_default_plan
from central_hub.signals import ensure_tenant_crm_defaults
from tenancy.bootstrap_context import skip_tenant_bootstrap_signals
from tenancy.signals import apply_tenant_entitlements
from tenancy.tenant_support import tenant_rls_context

logger = logging.getLogger(__name__)


def _load_job(job_id: str) -> ProvisioningJob:
    return ProvisioningJob.objects.select_related("tenant", "user").get(pk=job_id)


def _mark_job_failure(job_id: str, stage: str, exc: Exception) -> None:
    try:
        job = _load_job(job_id)
        job.mark_stage_failure(stage, str(exc))
    except Exception:
        logger.exception("Unable to persist provisioning failure for job=%s stage=%s", job_id, stage)


def _enqueue_next(task_callable, *args) -> None:
    task_callable.delay(*args)


@shared_task(bind=True, name="central_hub.tasks.create_tenant_for_provisioning", queue=settings.MEDIUM_PRIORITY_Q)
def create_tenant_for_provisioning(
    self,
    job_id: str,
    nombre: str,
    subdomain: str | None,
    domain: str,
    locale: str,
    email: str,
    username: str,
    password: str,
    first_name: str,
    last_name: str,
):
    stage = "tenant_creation"
    job = _load_job(job_id)
    job.mark_stage_running(stage)
    try:
        with transaction.atomic():
            default_plan = get_self_provision_default_plan()
            with skip_tenant_bootstrap_signals():
                tenant = Tenant.objects.create(
                    nombre=nombre,
                    domain=domain,
                    subdomain=subdomain or None,
                    plan=default_plan.key,
                    enabled=True,
                    organization_locale=(locale or "es").strip() or "es",
                )
            job.tenant = tenant
            job.save(update_fields=["tenant", "updated_at"])
        job.refresh_from_db(fields=["stages", "status", "current_stage"])
        job.mark_stage_success(stage)
        try:
            _enqueue_next(
                seed_tenant_for_provisioning,
                job_id,
                email,
                username,
                password,
                first_name,
                last_name,
                locale,
            )
        except Exception as exc:
            _mark_job_failure(job_id, "tenant_seeding", exc)
            raise
    except IntegrityError as exc:
        error_message = "Subdomain already taken." if "portal_tenant_subdomain_key" in str(exc) else str(exc)
        _mark_job_failure(job_id, stage, Exception(error_message))
        raise
    except Exception as exc:
        _mark_job_failure(job_id, stage, exc)
        raise


@shared_task(bind=True, name="central_hub.tasks.seed_tenant_for_provisioning", queue=settings.MEDIUM_PRIORITY_Q)
def seed_tenant_for_provisioning(
    self,
    job_id: str,
    email: str,
    username: str,
    password: str,
    first_name: str,
    last_name: str,
    locale: str,
):
    stage = "tenant_seeding"
    job = _load_job(job_id)
    job.mark_stage_running(stage)
    try:
        tenant = job.tenant
        if tenant is None:
            raise RuntimeError("Provisioning job has no tenant for seeding.")
        with transaction.atomic():
            default_plan = get_self_provision_default_plan()
            with tenant_rls_context(tenant.rls_slug):
                ensure_tenant_crm_defaults(tenant)
            tenant.plan = default_plan.key
            tenant.organization_locale = (locale or "es").strip() or "es"
            tenant.save(update_fields=["plan", "organization_locale"])
            apply_tenant_entitlements(tenant)
        job.refresh_from_db(fields=["stages", "status", "current_stage"])
        job.mark_stage_success(stage)
        try:
            _enqueue_next(
                create_primary_user_for_provisioning,
                job_id,
                email,
                username,
                password,
                first_name,
                last_name,
                locale,
            )
        except Exception as exc:
            _mark_job_failure(job_id, "primary_user_creation", exc)
            raise
    except Exception as exc:
        _mark_job_failure(job_id, stage, exc)
        raise


@shared_task(bind=True, name="central_hub.tasks.create_primary_user_for_provisioning", queue=settings.MEDIUM_PRIORITY_Q)
def create_primary_user_for_provisioning(
    self,
    job_id: str,
    email: str,
    username: str,
    password: str,
    first_name: str,
    last_name: str,
    locale: str,
):
    stage = "primary_user_creation"
    job = _load_job(job_id)
    job.mark_stage_running(stage)
    try:
        tenant = job.tenant
        if tenant is None:
            raise RuntimeError("Provisioning job has no tenant for primary user creation.")

        user_model = get_user_model()
        with transaction.atomic():
            user = user_model.objects.create_user(
                email=email,
                username=username,
                password=password,
                tenant=tenant,
                first_name=first_name or "",
                last_name=last_name or "",
            )
            group, _ = Group.objects.get_or_create(name="tenant_admin")
            user.groups.add(group)
            UserProfile.objects.update_or_create(
                user=user,
                defaults={
                    "display_name": f"{first_name} {last_name}".strip() or username,
                    "locale": (locale or "es").strip() or "es",
                    "timezone": "UTC",
                    "onboarding_state": "pending",
                    "default_landing": "/dashboard",
                },
            )
            job.user = user
            job.save(update_fields=["user", "updated_at"])
        job.refresh_from_db(fields=["stages", "status", "current_stage"])
        job.mark_stage_success(stage, final=True)
    except IntegrityError as exc:
        if "moiouser_email" in str(exc).lower() or "email" in str(exc).lower():
            error_message = "Email already registered."
        elif "username" in str(exc).lower():
            error_message = "Username already taken."
        else:
            error_message = str(exc)
        _mark_job_failure(job_id, stage, Exception(error_message))
        raise
    except Exception as exc:
        _mark_job_failure(job_id, stage, exc)
        raise


def _parse_kpi_period(period_key: str):
    """Return (start_dt, end_dt) for period_key. None, None for 'all'."""
    from django.utils import timezone
    now = timezone.now()
    if period_key == "24h":
        return now - timezone.timedelta(hours=24), now
    if period_key == "7d":
        return now - timezone.timedelta(days=7), now
    if period_key == "30d":
        return now - timezone.timedelta(days=30), now
    return None, None


@shared_task(
    bind=True,
    name="central_hub.tasks.refresh_platform_admin_kpi_snapshots",
    queue=settings.LOW_PRIORITY_Q,
)
def refresh_platform_admin_kpi_snapshots(
    self,
    period_keys: list[str] | None = None,
    tenant_slug: str | None = None,
    tenant_slugs: list[str] | None = None,
):
    """
    Aggregate KPIs into PlatformAdminKpiSnapshot (loop with tenant_rls_context per tenant).
    - tenant_slugs: optional list of rls_slugs (subdomains) to sweep. If provided, no tenant
      discovery in the worker; caller must pass the list (e.g. from get_enabled_tenants_for_kpis).
    - If tenant_slugs is not provided: tenant_slug=None means "all tenants", tenant_slug="acme"
      means that tenant only (list discovered via get_enabled_tenants_for_kpis in the task).
    period_keys: e.g. ["all", "24h", "7d", "30d"]. Default all four.
    """
    from central_hub.api.platform.kpi_aggregation import (
        get_enabled_tenants_for_kpis,
        run_full_sweep,
        run_full_sweep_over_slugs,
    )

    keys = period_keys or ["all", "24h", "7d", "30d"]
    tenant_id = None
    slugs_to_use = None

    if tenant_slugs:
        slugs_to_use = [s for s in tenant_slugs if (s or "").strip()]
        if not slugs_to_use:
            logger.warning("Platform KPI refresh: tenant_slugs empty, skipping")
            return
        logger.info(
            "Platform KPI refresh: using explicit tenant_slugs (%s): %s",
            len(slugs_to_use),
            slugs_to_use,
        )
        if len(slugs_to_use) == 1:
            tenant_list = get_enabled_tenants_for_kpis(slugs_to_use[0])
            if tenant_list:
                tenant_id = tenant_list[0][0]
    else:
        if tenant_slug:
            tenant_list = get_enabled_tenants_for_kpis(tenant_slug)
            if not tenant_list:
                logger.warning("Platform KPI refresh: tenant_slug=%s not found, skipping", tenant_slug)
                return
            tenant_id = tenant_list[0][0]

    for period_key in keys:
        start_dt, end_dt = _parse_kpi_period(period_key)
        if slugs_to_use is not None:
            totals = run_full_sweep_over_slugs(slugs_to_use, start_dt=start_dt, end_dt=end_dt)
        else:
            totals = run_full_sweep(tenant_slug=tenant_slug, start_dt=start_dt, end_dt=end_dt)
        total_activity_per_hour = None
        if start_dt is not None and end_dt is not None:
            delta = end_dt - start_dt
            hours = max(delta.total_seconds() / 3600.0, 1e-6)
            total_activity_per_hour = round(totals["activities"] / hours, 2)
        PlatformAdminKpiSnapshot.objects.update_or_create(
            tenant_id=tenant_id,
            period_key=period_key,
            defaults={
                "contacts": totals["contacts"],
                "accounts": totals["accounts"],
                "deals": totals["deals"],
                "activities": totals["activities"],
                "flow_executions": totals["flow_executions"],
                "agent_sessions": totals["agent_sessions"],
                "total_activity_per_hour": total_activity_per_hour,
            },
        )
        logger.info(
            "Platform KPI refresh period_key=%s: totals contacts=%s accounts=%s activities=%s",
            period_key,
            totals["contacts"],
            totals["accounts"],
            totals["activities"],
        )
    logger.info(
        "Platform admin KPI snapshots refreshed period_keys=%s tenant_slugs=%s",
        keys,
        slugs_to_use if slugs_to_use is not None else (f"discovered(tenant_slug={tenant_slug!r})"),
    )
