from __future__ import annotations

from django.contrib.auth import get_user_model
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import BasePermission, IsAuthenticated
from rest_framework.response import Response
from rest_framework_simplejwt.authentication import JWTAuthentication

from moio_platform.authentication import BearerTokenAuthentication
from central_hub.authentication import CsrfExemptSessionAuthentication, TenantJWTAAuthentication
from central_hub.capabilities import get_effective_capabilities
from central_hub.rbac import RequireHumanUser, user_has_role

from .serializers import MoioUserReadSerializer, MoioUserWriteSerializer

UserModel = get_user_model()


class HasCapability(BasePermission):
    """Allow if user has the given capability (users_manage, etc.) via effective capabilities."""

    def __init__(self, capability_key: str = "users_manage"):
        self.capability_key = capability_key

    def has_permission(self, request, view) -> bool:
        user = getattr(request, "user", None)
        if not user or not getattr(user, "is_authenticated", False):
            return False
        if getattr(user, "is_superuser", False) or user_has_role(user, "platform_admin"):
            return True
        tenant = getattr(user, "tenant", None)
        eff = get_effective_capabilities(user, tenant)
        return eff.can(self.capability_key)


class UserViewSet(viewsets.ModelViewSet):
    """
    Tenant-scoped CRUD for `tenancy.MoioUser`.

    Routes:
    - GET/POST   /api/v1/users/
    - GET/PATCH/PUT/DELETE /api/v1/users/{id}/
    """

    authentication_classes = [
        CsrfExemptSessionAuthentication,
        TenantJWTAAuthentication,
        BearerTokenAuthentication,
        JWTAuthentication,
    ]

    permission_classes = [IsAuthenticated, RequireHumanUser, HasCapability]

    queryset = UserModel.objects.all()

    def get_queryset(self):
        user = getattr(self.request, "user", None)
        if not user or not getattr(user, "is_authenticated", False):
            return UserModel.objects.none()

        if getattr(user, "is_superuser", False) or user_has_role(user, "platform_admin"):
            # Platform admins can optionally scope to a tenant via query param.
            tenant_id = self.request.query_params.get("tenant_id")
            if tenant_id:
                return UserModel.objects.filter(tenant_id=tenant_id).order_by("id")
            return UserModel.objects.all().order_by("id")

        tenant = getattr(user, "tenant", None)
        if tenant is None:
            return UserModel.objects.none()
        return UserModel.objects.filter(tenant=tenant).order_by("id")

    def get_serializer_class(self):
        if self.action in {"list", "retrieve"}:
            return MoioUserReadSerializer
        return MoioUserWriteSerializer

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        return Response(
            MoioUserReadSerializer(user, context={"request": request}).data,
            status=status.HTTP_201_CREATED,
        )

    def update(self, request, *args, **kwargs):
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=False, context={"request": request})
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        return Response(MoioUserReadSerializer(user, context={"request": request}).data)

    def partial_update(self, request, *args, **kwargs):
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=True, context={"request": request})
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        return Response(MoioUserReadSerializer(user, context={"request": request}).data)

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        if instance.pk == getattr(request.user, "pk", None):
            raise PermissionDenied("You cannot delete your own user")
        return super().destroy(request, *args, **kwargs)
