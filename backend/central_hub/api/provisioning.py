"""Self-provision: staged async workflow with live polling."""
from __future__ import annotations

import logging

from django.db import transaction
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from tenancy.validators import validate_subdomain_rfc

from central_hub.models import ProvisioningJob, Tenant
from central_hub.plan_policy import PlanPolicyError, get_self_provision_default_plan
from central_hub.authentication import TenantTokenObtainPairSerializer
from crm.api.auth.serializers import UserSerializer

logger = logging.getLogger(__name__)


class SelfProvisionView(APIView):
    """
    POST /api/v1/tenants/self-provision/
    Body: nombre, plan (optional), subdomain (optional), domain (optional),
          email, username, password, first_name (optional), last_name (optional).
    Returns: 202 Accepted with task_id. Poll GET /api/v1/tenants/provision-status/<task_id>/
    """
    permission_classes = [AllowAny]

    def post(self, request):
        from django.contrib.auth import get_user_model
        from central_hub.tasks import create_tenant_for_provisioning

        user_model = get_user_model()
        nombre = (request.data.get("nombre") or "").strip()
        email = (request.data.get("email") or "").strip()
        username = (request.data.get("username") or "").strip()
        password = request.data.get("password")
        subdomain = (request.data.get("subdomain") or "").strip() or None
        domain = (request.data.get("domain") or "moio.local").strip()
        first_name = (request.data.get("first_name") or "").strip()
        last_name = (request.data.get("last_name") or "").strip()
        locale = "es"

        if not nombre:
            return Response({"nombre": "Organization name is required."}, status=status.HTTP_400_BAD_REQUEST)
        if not email:
            return Response({"email": "Email is required."}, status=status.HTTP_400_BAD_REQUEST)
        if not username:
            return Response({"username": "Username is required."}, status=status.HTTP_400_BAD_REQUEST)
        if not password:
            return Response({"password": "Password is required."}, status=status.HTTP_400_BAD_REQUEST)

        if subdomain:
            try:
                validate_subdomain_rfc(subdomain)
            except ValueError as e:
                return Response({"subdomain": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        if subdomain and Tenant.objects.filter(subdomain=subdomain).exists():
            return Response({"subdomain": "Subdomain already taken."}, status=status.HTTP_400_BAD_REQUEST)
        if user_model.objects.filter(email__iexact=email).exists():
            return Response({"email": "Email already registered."}, status=status.HTTP_400_BAD_REQUEST)
        if user_model.objects.filter(username__iexact=username).exists():
            return Response({"username": "Username already taken."}, status=status.HTTP_400_BAD_REQUEST)
        try:
            default_plan = get_self_provision_default_plan()
        except PlanPolicyError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_503_SERVICE_UNAVAILABLE)

        try:
            with transaction.atomic():
                job = ProvisioningJob.objects.create(
                    requested_name=nombre,
                    requested_email=email,
                    requested_username=username,
                    requested_subdomain=subdomain or "",
                    requested_domain=domain,
                    requested_locale=locale,
                )
            create_tenant_for_provisioning.delay(
                str(job.pk),
                nombre,
                subdomain,
                domain,
                locale,
                email,
                username,
                password,
                first_name,
                last_name,
            )
            logger.info("Self-provision enqueued: job_id=%s", job.id)
        except Exception as e:
            if "job" in locals():
                try:
                    job.mark_stage_failure("tenant_creation", str(e))
                except Exception:
                    logger.exception("Failed to persist provisioning enqueue failure for job=%s", getattr(job, "id", None))
            logger.exception("Failed to queue self-provision task")
            return Response(
                {
                    "detail": "Provisioning could not be queued. Is Celery worker running?",
                    "error": str(e),
                },
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        return Response(
            {
                "task_id": str(job.id),
                "status": "pending",
                "current_stage": "tenant_creation",
                "plan_key": default_plan.key,
                "stages": job.stages,
                "message": "Provisioning started. Poll GET /api/v1/tenants/provision-status/{task_id}/",
                "poll_url": f"/api/v1/tenants/provision-status/{job.id}/",
            },
            status=status.HTTP_202_ACCEPTED,
        )


class ProvisionStatusView(APIView):
    """
    GET /api/v1/tenants/provision-status/<task_id>/
    Returns staged provisioning progress and, on success, the auth payload for the created user.
    """
    permission_classes = [AllowAny]

    def get(self, request, task_id):
        try:
            job = ProvisioningJob.objects.select_related("tenant", "user").get(pk=task_id)
        except ProvisioningJob.DoesNotExist:
            return Response({"detail": "Provisioning job not found."}, status=status.HTTP_404_NOT_FOUND)

        payload = {
            "task_id": str(job.pk),
            "status": job.status,
            "current_stage": job.current_stage,
            "stages": job.stages,
            "tenant_id": str(job.tenant_id) if job.tenant_id else None,
            "user_id": str(job.user_id) if job.user_id else None,
        }

        if job.status == "failure":
            return Response(
                {**payload, "error": job.error_message or "Provisioning failed"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        if job.status != "success" or job.user is None:
            return Response(payload, status=status.HTTP_202_ACCEPTED)

        refresh = TenantTokenObtainPairSerializer.get_token(job.user, tenant=job.tenant)
        user_data = UserSerializer(job.user, context={"request": request}).data
        return Response(
            {
                **payload,
                "access_token": str(refresh.access_token),
                "refresh_token": str(refresh),
                "token_type": "Bearer",
                "expires_in": 900,
                "user": user_data,
            },
            status=status.HTTP_200_OK,
        )
