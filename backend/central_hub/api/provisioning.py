"""
Self-provision: create tenant + first user (async via Celery, sync fallback).
"""
from __future__ import annotations

import logging

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView
from celery.result import AsyncResult

from tenancy.validators import validate_subdomain_rfc

from central_hub.models import Tenant, UserProfile
from central_hub.authentication import TenantTokenObtainPairSerializer
from crm.api.auth.serializers import UserSerializer

logger = logging.getLogger(__name__)
UserModel = get_user_model()


def _run_provision_sync(nombre, plan, subdomain, domain, email, username, password, first_name, last_name):
    """Synchronous provisioning (used when Celery unavailable)."""
    tenant = Tenant.objects.create(
        nombre=nombre,
        domain=domain,
        subdomain=subdomain or None,
        plan=plan,
        enabled=True,
    )
    user = UserModel.objects.create_user(
        email=email,
        username=username,
        password=password,
        tenant=tenant,
        first_name=first_name or "",
        last_name=last_name or "",
    )
    group, _ = Group.objects.get_or_create(name="tenant_admin")
    user.groups.add(group)
    UserProfile.objects.get_or_create(
        user=user,
        defaults={
            "display_name": f"{first_name} {last_name}".strip() or username,
            "locale": "en",
            "timezone": "UTC",
            "onboarding_state": "pending",
            "default_landing": "/dashboard",
        },
    )
    return tenant, user


class SelfProvisionView(APIView):
    """
    POST /api/v1/tenants/self-provision/
    Body: nombre, plan (optional), subdomain (optional), domain (optional),
          email, username, password, first_name (optional), last_name (optional).
    Returns: 202 Accepted with task_id. Poll GET /api/v1/tenants/provision-status/<task_id>/
    """
    permission_classes = [AllowAny]

    def post(self, request):
        nombre = (request.data.get("nombre") or "").strip()
        email = (request.data.get("email") or "").strip()
        username = (request.data.get("username") or "").strip()
        password = request.data.get("password")
        plan = (request.data.get("plan") or "free").strip().lower()
        subdomain = (request.data.get("subdomain") or "").strip() or None
        domain = (request.data.get("domain") or "moio.local").strip()
        first_name = (request.data.get("first_name") or "").strip()
        last_name = (request.data.get("last_name") or "").strip()

        if not nombre:
            return Response({"nombre": "Organization name is required."}, status=status.HTTP_400_BAD_REQUEST)
        if not email:
            return Response({"email": "Email is required."}, status=status.HTTP_400_BAD_REQUEST)
        if not username:
            return Response({"username": "Username is required."}, status=status.HTTP_400_BAD_REQUEST)
        if not password:
            return Response({"password": "Password is required."}, status=status.HTTP_400_BAD_REQUEST)
        if plan not in ("free", "pro", "business"):
            return Response({"plan": "Must be free, pro, or business."}, status=status.HTTP_400_BAD_REQUEST)

        if subdomain:
            try:
                validate_subdomain_rfc(subdomain)
            except ValueError as e:
                return Response({"subdomain": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        if subdomain and Tenant.objects.filter(subdomain=subdomain).exists():
            return Response({"subdomain": "Subdomain already taken."}, status=status.HTTP_400_BAD_REQUEST)
        if UserModel.objects.filter(email__iexact=email).exists():
            return Response({"email": "Email already registered."}, status=status.HTTP_400_BAD_REQUEST)
        if UserModel.objects.filter(username__iexact=username).exists():
            return Response({"username": "Username already taken."}, status=status.HTTP_400_BAD_REQUEST)

        use_sync = request.query_params.get("sync") == "1" or request.data.get("sync") is True
        broker = getattr(settings, "CELERY_BROKER_URL", "") or ""
        if use_sync or broker.startswith("memory://"):
            # Sync path: Celery memory broker doesn't work across processes
            logger.info("Self-provision running synchronously (sync=1 or memory broker)")
            try:
                tenant, user = _run_provision_sync(
                    nombre=nombre,
                    plan=plan,
                    subdomain=subdomain,
                    domain=domain,
                    email=email,
                    username=username,
                    password=password,
                    first_name=first_name,
                    last_name=last_name,
                )
            except Exception:
                logger.exception("Sync self-provision failed")
                return Response(
                    {"detail": "Provisioning failed. Please try again or contact support."},
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR,
                )
            refresh = TenantTokenObtainPairSerializer.get_token(user)
            user_data = UserSerializer(user, context={"request": request}).data
            return Response(
                {
                    "access_token": str(refresh.access_token),
                    "refresh_token": str(refresh),
                    "token_type": "Bearer",
                    "expires_in": 900,
                    "user": user_data,
                },
                status=status.HTTP_201_CREATED,
            )

        # Async path: enqueue Celery task
        from central_hub.tasks import self_provision_tenant_task

        try:
            task = self_provision_tenant_task.delay(
                nombre=nombre,
                plan=plan,
                subdomain=subdomain,
                domain=domain,
                email=email,
                username=username,
                password=password,
                first_name=first_name,
                last_name=last_name,
            )
            logger.info("Self-provision enqueued: task_id=%s", task.id)
        except Exception as e:
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
                "task_id": task.id,
                "status": "pending",
                "message": "Provisioning started. Poll GET /api/v1/tenants/provision-status/{task_id}/",
                "poll_url": f"/api/v1/tenants/provision-status/{task.id}/",
            },
            status=status.HTTP_202_ACCEPTED,
        )


class ProvisionStatusView(APIView):
    """
    GET /api/v1/tenants/provision-status/<task_id>/
    Returns: status (PENDING|STARTED|SUCCESS|FAILURE), and when SUCCESS: access_token, refresh_token, user.
    """
    permission_classes = [AllowAny]

    def get(self, request, task_id):
        result = AsyncResult(task_id)
        state = result.status

        if state == "SUCCESS":
            data = result.result
            if isinstance(data, dict):
                return Response(
                    {"status": "success", **data},
                    status=status.HTTP_200_OK,
                )
            return Response(
                {"status": "success", "result": data},
                status=status.HTTP_200_OK,
            )

        if state == "FAILURE":
            error = str(result.result) if result.result else "Provisioning failed"
            return Response(
                {"status": "failure", "error": error},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        return Response(
            {"status": state.lower(), "task_id": task_id},
            status=status.HTTP_202_ACCEPTED,
        )
