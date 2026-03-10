"""
GET /api/v1/bootstrap/ — single payload: user, profile, tenant, entitlements, capabilities, navigation.
"""
from __future__ import annotations

from typing import Any, Dict, List

from django.contrib.auth import get_user_model
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.authentication import JWTAuthentication

from crm.api.auth.serializers import UserSerializer
from moio_platform.authentication import BearerTokenAuthentication
from central_hub.authentication import CsrfExemptSessionAuthentication, TenantJWTAAuthentication
from central_hub.capabilities import get_effective_capabilities
from central_hub.models import UserProfile
from central_hub.rbac import RequireHumanUser

UserModel = get_user_model()


def _serialize_profile(profile: UserProfile | None) -> Dict[str, Any]:
    if profile is None:
        return {
            "display_name": "",
            "title": "",
            "department": "",
            "locale": "en",
            "timezone": "UTC",
            "onboarding_state": "pending",
            "default_landing": "/dashboard",
            "ui_preferences": {},
        }
    return {
        "display_name": profile.display_name or "",
        "title": profile.title or "",
        "department": profile.department or "",
        "locale": profile.locale or "en",
        "timezone": profile.timezone or "UTC",
        "onboarding_state": profile.onboarding_state or "pending",
        "default_landing": profile.default_landing or "/dashboard",
        "ui_preferences": profile.ui_preferences or {},
    }


def _serialize_tenant(user) -> Dict[str, Any] | None:
    tenant = getattr(user, "tenant", None)
    if tenant is None:
        return None
    return {
        "id": str(tenant.pk),
        "nombre": tenant.nombre,
        "plan": getattr(tenant, "plan", "free"),
        "enabled": getattr(tenant, "enabled", True),
    }


def _serialize_entitlements(tenant) -> Dict[str, Any]:
    if tenant is None:
        return {"features": {}, "limits": {}, "plan": "free", "ui": {}}
    return {
        "plan": getattr(tenant, "plan", "free") or "free",
        "features": getattr(tenant, "features", None) or {},
        "limits": getattr(tenant, "limits", None) or {},
        "ui": getattr(tenant, "ui", None) or {},
    }


def _filter_navigation(user) -> List[Dict[str, Any]]:
    """Return navigation items. AppMenu removed - returns empty list."""
    return []


class BootstrapView(APIView):
    """
    GET /api/v1/bootstrap/
    Returns: user, profile, tenant, entitlements, capabilities, navigation.
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

        profile = getattr(user, "profile", None)
        if profile is None and hasattr(UserProfile, "objects"):
            profile = UserProfile.objects.filter(user=user).first()

        eff = get_effective_capabilities(user, tenant)

        user_data = UserSerializer(user, context={"request": request}).data
        profile_data = _serialize_profile(profile)
        tenant_data = _serialize_tenant(user)
        entitlements_data = _serialize_entitlements(tenant)
        capabilities_data = {
            "allowed": sorted(eff.allowed_capabilities),
            "effective_features": eff.effective_features,
            "limits": eff.limits,
        }
        navigation_data = _filter_navigation(user)

        return Response({
            "user": user_data,
            "profile": profile_data,
            "tenant": tenant_data,
            "entitlements": entitlements_data,
            "capabilities": capabilities_data,
            "navigation": navigation_data,
        })
