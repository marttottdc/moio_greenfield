"""
Lightweight role helpers for DRF views.

Roles are backed by Django `Group` names. Order (low → high):
viewer < member < manager < tenant_admin < platform_admin

`is_superuser` always bypasses role checks.
"""
from __future__ import annotations

from functools import wraps
from typing import Iterable

from django.contrib.auth.models import Group
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import BasePermission


# Ordered list from lowest to highest privilege.
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
    """
    Returns True if the user has at least min_role.
    """
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
    """
    Decorator for DRF APIView methods to enforce role membership.
    """

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
                    {
                        "error": {
                            "code": "permission_denied",
                            "message": f"{min_role} role required.",
                        }
                    },
                    status=status.HTTP_403_FORBIDDEN,
                )

            return view_func(view_self, request, *args, **kwargs)

        return wrapper

    return decorator


class RequireHumanUser(BasePermission):
    """
    Reject service-to-service JWT (where request.auth is a dict payload).
    Allows only real authenticated users.
    """

    def has_permission(self, request, view):
        user = getattr(request, "user", None)
        if not user or not getattr(user, "is_authenticated", False):
            return False
        # ServiceJWTAuthentication sets request.auth to the decoded payload (dict).
        if isinstance(getattr(request, "auth", None), dict):
            return False
        return True

