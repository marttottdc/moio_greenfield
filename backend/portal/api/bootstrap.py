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
from portal.authentication import CsrfExemptSessionAuthentication, TenantJWTAAuthentication
from portal.capabilities import get_effective_capabilities
from portal.models import AppMenu, UserProfile
from portal.rbac import RequireHumanUser, _role_rank, _user_group_names, ROLE_ORDER

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


def _menu_item_payload(menu: AppMenu) -> Dict[str, Any]:
    return {
        "id": str(menu.id),
        "app": menu.app,
        "url": menu.url,
        "type": menu.type,
        "title": menu.title,
        "description": menu.description or "",
        "target_area": menu.target_area or "",
        "icon": menu.icon or "",
        "context": menu.context or "",
    }


def _filter_navigation(user) -> List[Dict[str, Any]]:
    """Return AppMenu items the user is allowed to see (by perm_group role)."""
    group_names = list(_user_group_names(user))
    user_highest_rank = max(
        (_role_rank(name) for name in group_names),
        default=-1,
    )
    if getattr(user, "is_superuser", False):
        user_highest_rank = _role_rank("platform_admin")

    items = []
    for menu in AppMenu.objects.filter(enabled=True).order_by("app", "title"):
        required = (menu.perm_group or "").strip().lower()
        if not required:
            items.append(_menu_item_payload(menu))
            continue
        if required not in ROLE_ORDER:
            continue
        required_rank = _role_rank(required)
        if required_rank >= 0 and user_highest_rank >= required_rank:
            items.append(_menu_item_payload(menu))
    return items


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
