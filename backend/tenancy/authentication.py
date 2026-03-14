"""Authentication: UserApiKey, JWT with tenant claims."""
import hashlib
import logging
from typing import Any

from django.utils import timezone
from rest_framework import authentication
from rest_framework.authentication import SessionAuthentication
from rest_framework.exceptions import AuthenticationFailed
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from rest_framework_simplejwt.exceptions import InvalidToken

from tenancy.context_utils import current_tenant
from tenancy.models import UserApiKey
from tenancy.resolution import (
    TenantResolutionError,
    _current_connection_schema,
    bind_request_tenant,
    ensure_request_tenant_context,
    route_requires_tenant,
)

_log = logging.getLogger("tenancy_trace")

try:
    from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken
except Exception:  # pragma: no cover
    BlacklistedToken = None


def _resolve_request_tenant(request, fallback=None):
    tenant = getattr(request, "tenant", None) if request is not None else None
    schema_name = str(getattr(tenant, "schema_name", "") or "").strip()
    if tenant is not None and schema_name and schema_name != "public":
        return tenant
    return fallback


def _apply_tenant_claims(token, tenant) -> None:
    if tenant:
        token["tenant_id"] = str(tenant.id)
        token["tenant_schema"] = str(getattr(tenant, "schema_name", "") or "")
        token["tenant_code"] = str(getattr(tenant, "tenant_code", "") or "")
    else:
        token["tenant_id"] = None
        token["tenant_schema"] = None
        token["tenant_code"] = None


class UserApiKeyAuthentication(authentication.BaseAuthentication):
    """Authenticate using a user API key (Bearer moio_xxx)."""

    keyword = "Bearer"

    def authenticate(self, request):
        auth_header = request.META.get("HTTP_AUTHORIZATION")
        if not auth_header or not auth_header.startswith(f"{self.keyword} "):
            return None

        raw_token = auth_header[len(self.keyword) :].strip()
        if not raw_token.startswith("moio_"):
            return None

        key_hash = hashlib.sha256(raw_token.encode()).hexdigest()
        try:
            api_key = UserApiKey.objects.select_related("user", "tenant").get(
                key_hash=key_hash,
                is_active=True,
            )
        except UserApiKey.DoesNotExist:
            raise AuthenticationFailed("Invalid API key")

        if not api_key.user.is_active:
            raise AuthenticationFailed("User account is disabled")

        if api_key.expires_at and timezone.now() > api_key.expires_at:
            raise AuthenticationFailed("API key has expired")

        try:
            tenant = ensure_request_tenant_context(
                request,
                user=getattr(api_key, "user", None),
                require_tenant=route_requires_tenant(request),
            )
        except TenantResolutionError as exc:
            raise AuthenticationFailed(str(exc)) from exc
        if tenant is None:
            tenant = _resolve_request_tenant(request, api_key.tenant)
            bind_request_tenant(
                request,
                tenant,
                user=getattr(api_key, "user", None),
                source=getattr(request, "tenant_resolution_source", None) or "api_key",
                route_policy=getattr(request, "tenant_route_policy", None),
            )

        api_key.last_used_at = timezone.now()
        api_key.save(update_fields=["last_used_at"])

        return (api_key.user, api_key)

    def authenticate_header(self, request):
        return 'Bearer realm="api"'


class CsrfExemptSessionAuthentication(SessionAuthentication):
    """Session authentication without CSRF enforcement for API endpoints."""

    def enforce_csrf(self, request):
        return


class TenantJWTAAuthentication(JWTAuthentication):
    def authenticate(self, request):
        result = super().authenticate(request)
        if result is None:
            return None
        user, validated_token = result
        try:
            tenant = ensure_request_tenant_context(
                request,
                user=user,
                require_tenant=route_requires_tenant(request),
            )
        except TenantResolutionError as exc:
            raise AuthenticationFailed(str(exc)) from exc
        if tenant is None:
            bind_request_tenant(
                request,
                _resolve_request_tenant(request, getattr(user, "tenant", None)),
                user=user,
                source=getattr(request, "tenant_resolution_source", None) or "user",
                route_policy=getattr(request, "tenant_route_policy", None),
            )
        _log.debug(
            "TenantJWTAAuthentication: request.tenant=%s user.tenant_id=%s conn_schema=%s",
            getattr(request, "tenant", None) and getattr(getattr(request, "tenant", None), "schema_name", ""),
            getattr(user, "tenant_id", None),
            _current_connection_schema(),
        )
        return user, validated_token

    def get_validated_token(self, raw_token):
        token = super().get_validated_token(raw_token)
        if BlacklistedToken is not None and hasattr(BlacklistedToken, "objects"):
            jti = token.get("jti")
            if jti and BlacklistedToken.objects.filter(token__jti=jti).exists():
                raise InvalidToken("Token is blacklisted")
        return token

    def get_user(self, validated_token):
        user = super().get_user(validated_token)
        current_tenant.set(getattr(user, "tenant", None))
        return user


class TenantTokenObtainPairSerializer(TokenObtainPairSerializer):
    """Custom JWT serializer that includes tenant_id in the token claims."""

    @classmethod
    def get_token(
        cls,
        user,
        *,
        tenant=None,
        session_mode: str | None = None,
        platform_actor: dict[str, Any] | None = None,
    ):
        token = super().get_token(user)
        effective_tenant = tenant if tenant is not None else getattr(user, "tenant", None)
        _apply_tenant_claims(token, effective_tenant)
        if session_mode:
            token["session_mode"] = session_mode
        if platform_actor:
            token["platform_actor"] = platform_actor
        return token
