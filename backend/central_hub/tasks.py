"""Celery tasks for central_hub (e.g. async self-provision)."""
from __future__ import annotations

import logging

from celery import shared_task
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.db import IntegrityError, transaction

from central_hub.integrations.shopify import tasks as _shopify_tasks  # noqa: F401,E402
from central_hub.models import ProvisioningJob, Tenant, UserProfile
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


@shared_task(bind=True, name="central_hub.tasks.create_tenant_for_provisioning")
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


@shared_task(bind=True, name="central_hub.tasks.seed_tenant_for_provisioning")
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


@shared_task(bind=True, name="central_hub.tasks.create_primary_user_for_provisioning")
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
