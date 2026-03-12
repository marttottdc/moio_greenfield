"""
Lightweight role helpers for DRF views.
Roles: viewer < member < manager < tenant_admin < platform_admin
"""
from __future__ import annotations

from functools import wraps
from typing import Iterable

from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import BasePermission

ROLE_ORDER = [
    "viewer",
    "member",
    "manager",
    "tenant_admin",
    "platform_admin",
]


def _role_rank(role: str | None) -> int:
    if role is None:
        return -1
    role_lc = role.lower()
    try:
        return ROLE_ORDER.index(role_lc)
    except ValueError:
        return -1


def _user_group_names(user) -> Iterable[str]:
    try:
        return (g.name.lower() for g in user.groups.all())
    except Exception:
        return []


def user_has_role(user, min_role: str) -> bool:
    if not user or not getattr(user, "is_authenticated", False):
        return False
    if getattr(user, "is_superuser", False):
        return True
    required_rank = _role_rank(min_role)
    if required_rank < 0:
        raise ValueError(f"Unknown role: {min_role}")
    highest_rank = max((_role_rank(name) for name in _user_group_names(user)), default=-1)
    return highest_rank >= required_rank


def require_role(min_role: str):
    def decorator(view_func):
        @wraps(view_func)
        def wrapper(view_self, request, *args, **kwargs):
            user = getattr(request, "user", None)
            if not user or not getattr(user, "is_authenticated", False):
                return Response(
                    {"error": {"code": "unauthenticated", "message": "Authentication required."}},
                    status=status.HTTP_401_UNAUTHORIZED,
                )
            if not user_has_role(user, min_role):
                return Response(
                    {"error": {"code": "permission_denied", "message": f"{min_role} role required."}},
                    status=status.HTTP_403_FORBIDDEN,
                )
            return view_func(view_self, request, *args, **kwargs)
        return wrapper
    return decorator


class RequireHumanUser(BasePermission):
    """Reject service-to-service JWT. Allows only real authenticated users."""

    def has_permission(self, request, view):
        user = getattr(request, "user", None)
        if not user or not getattr(user, "is_authenticated", False):
            return False
        if isinstance(getattr(request, "auth", None), dict):
            return False
        return True


class RequireTenantAccess(BasePermission):
    """
    Require the user to have a real tenant (not None, not public schema).
    Users with no tenant or public-only tenant have no access to tenant-scoped APIs.
    Superusers with no tenant are platform-admin only; they must use /api/platform/*.
    """

    message = "No tenant access. Use platform admin at /platform-admin if you are a platform administrator."
    code = "no_tenant_access"

    def has_permission(self, request, view):
        user = getattr(request, "user", None)
        if not user or not getattr(user, "is_authenticated", False):
            return False
        tenant = getattr(user, "tenant", None)
        if tenant is None:
            return False
        schema = str(getattr(tenant, "schema_name", "") or "").strip().lower()
        from tenancy.tenant_support import public_schema_name
        if schema == public_schema_name().lower():
            return False
        return True
