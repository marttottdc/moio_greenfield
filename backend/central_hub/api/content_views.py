"""
Minimal content API for frontend (e.g. sidebar navigation).
GET /api/v1/content/navigation/ returns menu hierarchy; empty list lets frontend use its default menu.
"""
from __future__ import annotations

from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.authentication import JWTAuthentication

from central_hub.authentication import TenantJWTAAuthentication
from moio_platform.authentication import BearerTokenAuthentication


class NavigationView(APIView):
    """
    GET /api/v1/content/navigation/
    Returns { "items": [] } so the sidebar uses its built-in default menu.
    Can be extended later with DB-driven or entitlement-based menu items.
    """
    authentication_classes = [
        TenantJWTAAuthentication,
        BearerTokenAuthentication,
        JWTAuthentication,
    ]
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response({"items": [], "version": "1"})
