from django.conf import settings
from django.contrib.auth import get_user_model
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt
from django.utils import timezone
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from crm.api.auth.serializers import UserSerializer
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.tokens import AccessToken, RefreshToken
from rest_framework.authtoken.models import Token

from central_hub.authentication import TenantTokenObtainPairSerializer
from central_hub.authentication import TenantJWTAAuthentication
from central_hub.models import UserApiKey

try:
    from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken, OutstandingToken
except Exception:  # pragma: no cover
    BlacklistedToken = None
    OutstandingToken = None


@method_decorator(csrf_exempt, name="dispatch")
class AuthViewSet(viewsets.ViewSet):
    permission_classes = [IsAuthenticated]  # 🔹 Let DRF’s JWTAuthentication handle this

    def get_permissions(self):
        # login and refresh must allow unauthenticated requests so clients can obtain a token.
        # All other actions (me, logout, etc.) require IsAuthenticated.
        if getattr(self, "action", None) in ("login", "refresh"):
            return [AllowAny()]
        return [IsAuthenticated()]

    @action(detail=False, methods=["get"], url_path="me")
    def me(self, request):
        serializer = UserSerializer(request.user, context={"request": request})
        return Response(serializer.data)

    @action(
        detail=False,
        methods=["post"],
        url_path="login",
        permission_classes=[AllowAny],
        authentication_classes=[],
    )
    def login(self, request):
        """
        POST /api/v1/auth/login/
        Body: username|email, password
        Returns: access, refresh
        """
        UserModel = get_user_model()
        username = (request.data.get("username") or request.data.get("email") or "").strip()
        raw_pw = request.data.get("password")
        password = (raw_pw if isinstance(raw_pw, str) else str(raw_pw or "")).strip()
        if not username or not password:
            return Response({"error": "invalid_request"}, status=status.HTTP_400_BAD_REQUEST)

        def _find_user():
            return (
                UserModel.objects.filter(email__iexact=username).first()
                or UserModel.objects.filter(username__iexact=username).first()
            )

        # With django_tenants, ensure we query the public schema (users live there)
        if getattr(settings, "DJANGO_TENANTS_ENABLED", False):
            try:
                from django_tenants.utils import schema_context
                with schema_context("public"):
                    user = _find_user()
            except Exception:
                user = _find_user()
        else:
            user = _find_user()

        if not user:
            return Response({"error": "invalid_credentials"}, status=status.HTTP_401_UNAUTHORIZED)
        if not user.check_password(password):
            return Response({"error": "invalid_credentials"}, status=status.HTTP_401_UNAUTHORIZED)

        refresh = TenantTokenObtainPairSerializer.get_token(user)
        access = str(refresh.access_token)
        refresh_str = str(refresh)
        # NOTE: match SimpleJWT default response shape (prod).

        Token.objects.get_or_create(user=user)
        return Response(
            {
                "access": access,
                "refresh": refresh_str,
            },
            status=status.HTTP_200_OK,
        )

    @action(
        detail=False,
        methods=["post"],
        url_path="refresh",
        permission_classes=[AllowAny],
        authentication_classes=[],
    )
    def refresh(self, request):
        """
        POST /api/v1/auth/refresh/
        Body: refresh
        Returns: access, refresh (new refresh token; client must replace stored refresh — tokens rotate and are blacklisted after use).
        """
        raw = (request.data.get("refresh") or "").strip()
        if not raw:
            return Response({"error": "invalid_refresh_token"}, status=status.HTTP_401_UNAUTHORIZED)

        try:
            old = RefreshToken(raw)
        except TokenError:
            return Response({"error": "invalid_refresh_token"}, status=status.HTTP_401_UNAUTHORIZED)

        # Invalidate old refresh token if blacklist is enabled (rotation: each refresh is single-use).
        try:
            old.blacklist()
        except Exception:
            # If blacklist app isn't enabled, we still rotate but can't enforce single-use.
            pass

        user_id = old.get("user_id")
        if not user_id:
            return Response({"error": "invalid_refresh_token"}, status=status.HTTP_401_UNAUTHORIZED)

        UserModel = get_user_model()
        user = UserModel.objects.filter(id=user_id).first()
        if not user:
            return Response({"error": "invalid_refresh_token"}, status=status.HTTP_401_UNAUTHORIZED)

        refresh = TenantTokenObtainPairSerializer.get_token(user)
        return Response(
            {
                "access": str(refresh.access_token),
                "refresh": str(refresh),
            },
            status=status.HTTP_200_OK,
        )

    @action(detail=False, methods=["get", "post", "delete"], url_path="api-key")
    def api_key(self, request):
        """GET: current key info (masked). POST: create/replace key. DELETE: revoke key. Requires JWT."""
        if isinstance(getattr(request, "auth", None), UserApiKey):
            return Response(
                {"error": "Use JWT to manage API keys; API key cannot be used for this action."},
                status=status.HTTP_403_FORBIDDEN,
            )
        if request.method == "GET":
            try:
                api_key = UserApiKey.objects.get(user=request.user, is_active=True)
            except UserApiKey.DoesNotExist:
                return Response(
                    {"error": "No active API key found"},
                    status=status.HTTP_404_NOT_FOUND,
                )
            return Response({
                "id": api_key.id,
                "name": api_key.name,
                "masked_key": api_key.masked_key,
                "created_at": api_key.created_at,
                "last_used_at": api_key.last_used_at,
                "expires_at": api_key.expires_at,
            })

        if request.method == "POST":
            if not getattr(request.user, "tenant_id", None):
                return Response(
                    {"error": "User must belong to a tenant to create an API key"},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            name = request.data.get("name", "API Key")
            api_key, created = UserApiKey.objects.get_or_create(
                user=request.user,
                defaults={"tenant": request.user.tenant, "name": name},
            )
            if not created:
                api_key.name = name
                api_key.tenant = request.user.tenant
                api_key.is_active = True
                api_key.created_at = timezone.now()
                api_key.last_used_at = None
            plain_key = api_key.generate_key()
            api_key.save()
            return Response(
                {
                    "id": api_key.id,
                    "name": api_key.name,
                    "key": plain_key,
                    "masked_key": api_key.masked_key,
                    "created_at": api_key.created_at,
                    "expires_at": api_key.expires_at,
                    "warning": "Save this key securely - it will not be shown again.",
                },
                status=status.HTTP_201_CREATED,
            )

        if request.method == "DELETE":
            updated = UserApiKey.objects.filter(
                user=request.user, is_active=True
            ).update(is_active=False)
            if updated == 0:
                return Response(
                    {"error": "No active API key to revoke"},
                    status=status.HTTP_404_NOT_FOUND,
                )
            return Response({"message": "API key revoked successfully"})

    @action(detail=False, methods=["post"], url_path="logout", permission_classes=[IsAuthenticated])
    def logout(self, request):
        # Revoke the current access token by blacklisting its jti (if enabled).
        authz = request.META.get("HTTP_AUTHORIZATION") or ""
        if authz.lower().startswith("bearer "):
            raw = authz.split(" ", 1)[1].strip()
            if raw and OutstandingToken is not None and BlacklistedToken is not None:
                try:
                    token = AccessToken(raw)
                    jti = token.get("jti")
                    exp = token.get("exp")
                    if jti and exp:
                        from datetime import datetime, timezone as dt_timezone

                        expires_at = datetime.fromtimestamp(int(exp), tz=dt_timezone.utc)
                        outstanding, _ = OutstandingToken.objects.get_or_create(
                            jti=jti,
                            defaults={"token": raw, "user": request.user, "expires_at": expires_at},
                        )
                        BlacklistedToken.objects.get_or_create(token=outstanding)
                except Exception:
                    pass
        return Response({"message": "Successfully logged out"}, status=status.HTTP_200_OK)

    def list(self, request, *args, **kwargs):
        return Response(status=status.HTTP_405_METHOD_NOT_ALLOWED)
