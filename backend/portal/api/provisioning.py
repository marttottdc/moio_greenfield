"""
Self-provision: create tenant + first user + profile + entitlements atomically.
"""
from __future__ import annotations

from django.contrib.auth import get_user_model
from django.db import transaction
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from portal.models import Tenant, MoioUser, UserProfile
from portal.authentication import TenantTokenObtainPairSerializer
from crm.api.auth.serializers import UserSerializer

UserModel = get_user_model()


def self_provision_tenant(
    *,
    nombre: str,
    plan: str = "free",
    subdomain: str | None = None,
    domain: str = "moio.local",
    email: str,
    username: str,
    password: str,
    first_name: str = "",
    last_name: str = "",
) -> tuple[Tenant, MoioUser]:
    """
    Create tenant (signals create TenantConfiguration and seed Tenant.features/limits/ui),
    then first user (tenant_admin) and profile in one transaction.
    Returns (tenant, user).
    """
    with transaction.atomic():
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
        from django.contrib.auth.models import Group
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
    Returns: access_token, refresh_token, token_type, expires_in, user.
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

        if subdomain and Tenant.objects.filter(subdomain=subdomain).exists():
            return Response({"subdomain": "Subdomain already taken."}, status=status.HTTP_400_BAD_REQUEST)
        if UserModel.objects.filter(email__iexact=email).exists():
            return Response({"email": "Email already registered."}, status=status.HTTP_400_BAD_REQUEST)
        if UserModel.objects.filter(username__iexact=username).exists():
            return Response({"username": "Username already taken."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            tenant, user = self_provision_tenant(
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
            return Response(
                {"detail": "Provisioning failed. Please try again or contact support."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        refresh = TenantTokenObtainPairSerializer.get_token(user)
        access = str(refresh.access_token)
        refresh_str = str(refresh)
        expires_in = 900  # default JWT access TTL

        user_data = UserSerializer(user, context={"request": request}).data
        return Response(
            {
                "access_token": access,
                "refresh_token": refresh_str,
                "token_type": "Bearer",
                "expires_in": expires_in,
                "user": user_data,
            },
            status=status.HTTP_201_CREATED,
        )
