"""
Celery tasks for central_hub (e.g. async self-provision).
"""
from __future__ import annotations

import logging
from celery import shared_task
from django.conf import settings

logger = logging.getLogger(__name__)


@shared_task(bind=True, name="central_hub.tasks.self_provision_tenant")
def self_provision_tenant_task(
    self,
    *,
    nombre: str,
    plan: str,
    subdomain: str | None,
    domain: str,
    email: str,
    username: str,
    password: str,
    first_name: str,
    last_name: str,
):
    """
    Create tenant + first user in background (migrations run here).
    Returns dict with access_token, refresh_token, user on success.
    Raises on failure (Celery will store the exception).
    """
    from django.contrib.auth import get_user_model
    from django.contrib.auth.models import Group

    from central_hub.models import Tenant, UserProfile
    from central_hub.authentication import TenantTokenObtainPairSerializer
    from crm.api.auth.serializers import UserSerializer

    UserModel = get_user_model()

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

    refresh = TenantTokenObtainPairSerializer.get_token(user)
    access = str(refresh.access_token)
    refresh_str = str(refresh)

    # Build minimal user_data without request context (serializer prefers request for avatar_url etc.)
    user_data = {
        "id": user.id,
        "email": user.email,
        "username": user.username,
        "first_name": user.first_name,
        "last_name": user.last_name,
        "organization": {
            "id": str(tenant.pk),
            "name": tenant.nombre,
            "domain": str(tenant.domain or ""),
            "subdomain": str(tenant.subdomain or ""),
            "primary_domain": str(tenant.primary_domain or ""),
            "schema_name": str(getattr(tenant, "schema_name", "") or ""),
        },
    }

    return {
        "access_token": access,
        "refresh_token": refresh_str,
        "token_type": "Bearer",
        "expires_in": 900,
        "user": user_data,
    }
