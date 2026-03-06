"""
Integration API Views

Provides REST API endpoints for managing integration configurations.
Uses registry-backed resolution for dynamic schema validation.
"""

from __future__ import annotations

from typing import Any

from django.db import IntegrityError
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView
from drf_spectacular.utils import extend_schema, OpenApiParameter, OpenApiExample

from portal.authentication import CsrfExemptSessionAuthentication, TenantJWTAAuthentication
from security.authentication import ServiceJWTAuthentication
from portal.integrations.models import IntegrationConfig
from portal.integrations.registry import (
    INTEGRATION_REGISTRY,
    get_integration,
    get_integration_schema,
    get_sensitive_fields,
    list_integrations,
    list_categories,
)
from portal.models import PortalConfiguration, TenantConfiguration
from chatbot.lib.whatsapp_client_api import (
    subscribe_to_webhooks,
    register_waba_phone_number,
)

import logging
import requests
from urllib.parse import urljoin

logger = logging.getLogger(__name__)
from portal.integrations.serializers import (
    IntegrationConfigSerializer,
    IntegrationConfigCreateSerializer,
    IntegrationConfigUpdateSerializer,
    IntegrationListSerializer,
    IntegrationSchemaSerializer,
)


class IntegrationAPIView(APIView):
    """Base view for integration API endpoints."""
    
    authentication_classes = [
        CsrfExemptSessionAuthentication,
        TenantJWTAAuthentication,
        ServiceJWTAuthentication,
    ]
    
    def get_tenant(self):
        """Get tenant from authenticated user."""
        return getattr(self.request.user, "tenant", None)


@method_decorator(csrf_exempt, name="dispatch")
class IntegrationListView(IntegrationAPIView):
    """
    List available integrations and their configuration status.
    
    Returns all integration types from the registry with their
    current configuration status for the authenticated tenant.
    """
    
    @extend_schema(
        summary="List available integrations",
        description="Get all available integration types with their configuration status for the current tenant",
        parameters=[
            OpenApiParameter(
                name="category",
                description="Filter by category (ai, messaging, payments, etc.)",
                type=str,
                required=False,
            ),
        ],
        responses={200: IntegrationListSerializer(many=True)},
        tags=["Integrations"],
        examples=[
            OpenApiExample(
                name="Integration list response",
                response_only=True,
                value=[
                    {
                        "slug": "whatsapp",
                        "name": "WhatsApp Business",
                        "description": "Customer messaging via WhatsApp Business API",
                        "category": "messaging",
                        "icon": "message-circle",
                        "supports_multi_instance": True,
                        "is_configured": True,
                        "enabled": True,
                        "instance_count": 2,
                    },
                    {
                        "slug": "openai",
                        "name": "OpenAI",
                        "description": "AI-powered assistance and automation",
                        "category": "ai",
                        "icon": "brain",
                        "supports_multi_instance": True,
                        "is_configured": True,
                        "enabled": True,
                        "instance_count": 1,
                    },
                ],
            ),
        ],
    )
    def get(self, request):
        tenant = self.get_tenant()
        if not tenant:
            return Response(
                {"error": "Authentication required"},
                status=status.HTTP_401_UNAUTHORIZED,
            )
        
        category = request.query_params.get("category")
        integrations = list_integrations(category)
        
        result = []
        for definition in integrations:
            configs = IntegrationConfig.objects.filter(
                tenant=tenant,
                slug=definition.slug,
            )
            
            enabled_count = configs.filter(enabled=True).count()
            configured_count = sum(1 for c in configs if c.is_configured())
            
            result.append({
                "slug": definition.slug,
                "name": definition.name,
                "description": definition.description,
                "category": definition.category,
                "icon": definition.icon,
                "supports_multi_instance": definition.supports_multi_instance,
                "is_configured": configured_count > 0,
                "enabled": enabled_count > 0,
                "instance_count": configs.count(),
            })
        
        return Response(result)


@method_decorator(csrf_exempt, name="dispatch")
class IntegrationSchemaView(IntegrationAPIView):
    """
    Get schema/field definitions for a specific integration type.
    """
    
    @extend_schema(
        summary="Get integration schema",
        description="Get field definitions and validation schema for an integration type",
        responses={200: IntegrationSchemaSerializer},
        tags=["Integrations"],
        examples=[
            OpenApiExample(
                name="WhatsApp schema",
                response_only=True,
                value={
                    "slug": "whatsapp",
                    "name": "WhatsApp Business",
                    "description": "Customer messaging via WhatsApp Business API",
                    "category": "messaging",
                    "fields": [
                        {"name": "token", "type": "string", "required": True, "sensitive": True, "description": "WhatsApp API access token"},
                        {"name": "phone_id", "type": "string", "required": True, "description": "WhatsApp phone number ID"},
                        {"name": "business_account_id", "type": "string", "required": True, "description": "WhatsApp Business Account ID"},
                    ],
                    "required_fields": ["token", "phone_id", "business_account_id"],
                    "sensitive_fields": ["token"],
                },
            ),
        ],
    )
    def get(self, request, slug: str):
        definition = get_integration(slug)
        if not definition:
            return Response(
                {"error": f"Unknown integration: {slug}"},
                status=status.HTTP_404_NOT_FOUND,
            )
        
        fields = []
        for f in definition.fields:
            fields.append({
                "name": f.name,
                "type": f.field_type,
                "required": f.required,
                "sensitive": f.sensitive,
                "default": f.default,
                "description": f.description,
            })
        
        return Response({
            "slug": definition.slug,
            "name": definition.name,
            "description": definition.description,
            "category": definition.category,
            "fields": fields,
            "required_fields": definition.get_required_fields(),
            "sensitive_fields": definition.get_sensitive_fields(),
        })


# ---------------------------------------------------------------------------
# WhatsApp Embedded Signup endpoints (for React frontend)
# ---------------------------------------------------------------------------


def _build_redirect_uri(portal_config: PortalConfiguration) -> str:
    """Return the public redirect URI for the new embedded-signup callback."""
    base = (portal_config.my_url or "").rstrip("/") + "/"
    return urljoin(base, "api/v1/integrations/whatsapp/embedded-signup/callback/")


def _register_phone_with_pin(phone_waba_id: str, fb_system_token: str, pin: str | None = None) -> dict:
    """
    Register a WABA phone number, allowing an optional PIN override.
    Falls back to the legacy helper if no custom PIN is provided.
    """
    if not pin:
        return register_waba_phone_number(phone_waba_id, fb_system_token)

    url = f"https://graph.facebook.com/v21.0/{phone_waba_id}/register"
    payload = {
        "messaging_product": "whatsapp",
        "pin": pin,
        "access_token": fb_system_token,
    }
    response = requests.post(url, json=payload)
    result = response.json()
    if not isinstance(result, dict):
        raise ValueError(f"Unexpected response registering phone: {result!r}")
    return result


@method_decorator(csrf_exempt, name="dispatch")
class WhatsappEmbeddedSignupConfigView(IntegrationAPIView):
    """
    Return frontend configuration for WhatsApp Embedded Signup.
    Supplies app_id, config_id, redirect_uri and extras.
    """

    @extend_schema(
        summary="WhatsApp Embedded Signup config",
        tags=["Integrations", "WhatsApp"],
        responses={200: dict},
    )
    def get(self, request):
        portal_config = PortalConfiguration.objects.first()
        if not portal_config:
            return Response(
                {"error": "PortalConfiguration not found"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        redirect_uri = _build_redirect_uri(portal_config)

        data = {
            "app_id": portal_config.fb_moio_bot_app_id,
            "config_id": portal_config.fb_moio_bot_configuration_id,
            "sdk_version": "v24.0",
            "redirect_uri": redirect_uri,
            "extras": {
                "feature": "whatsapp_embedded_signup",
                "sessionInfoVersion": 3,
                "version": "v3",
            },
        }
        return Response(data)


@method_decorator(csrf_exempt, name="dispatch")
class WhatsappEmbeddedSignupCompleteView(IntegrationAPIView):
    """
    Complete the Embedded Signup flow:
    - exchange code -> access_token
    - optionally subscribe webhooks and register phone
    - upsert IntegrationConfig using instance_id = phone_number_id
    """

    @extend_schema(
        summary="Complete WhatsApp Embedded Signup",
        tags=["Integrations", "WhatsApp"],
        responses={200: dict, 400: dict, 401: dict, 500: dict},
    )
    def post(self, request):
        tenant = self.get_tenant()
        if not tenant:
            return Response({"error": "Authentication required"}, status=status.HTTP_401_UNAUTHORIZED)

        code = request.data.get("code")
        phone_number_id = request.data.get("phone_number_id")
        waba_id = request.data.get("waba_id")
        display_phone_number = request.data.get("display_phone_number")
        verified_name = request.data.get("verified_name")
        instance_name = request.data.get("instance_name") or display_phone_number or verified_name or ""
        set_as_default = bool(request.data.get("set_as_default"))
        pin = request.data.get("pin")

        if not code or not phone_number_id or not waba_id:
            return Response(
                {"error": "code, phone_number_id and waba_id are required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        portal_config = PortalConfiguration.objects.first()
        if not portal_config or not portal_config.fb_moio_bot_app_id or not portal_config.fb_moio_bot_app_secret:
            return Response(
                {"error": "PortalConfiguration missing Facebook app credentials"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        redirect_uri = _build_redirect_uri(portal_config)

        # Exchange code -> access_token
        try:
            token_resp = requests.get(
                "https://graph.facebook.com/v21.0/oauth/access_token",
                params={
                    "client_id": portal_config.fb_moio_bot_app_id,
                    "client_secret": portal_config.fb_moio_bot_app_secret,
                    "redirect_uri": redirect_uri,
                    "code": code,
                },
            )
            token_resp.raise_for_status()
            token_payload = token_resp.json()
            access_token = token_payload.get("access_token")
            if not access_token:
                return Response(
                    {"error": f"No access_token in response: {token_payload!r}"},
                    status=status.HTTP_502_BAD_GATEWAY,
                )
        except requests.HTTPError as exc:
            logger.exception("OAuth exchange failed")
            return Response({"error": "OAuth exchange failed", "details": str(exc)}, status=token_resp.status_code)
        except Exception as exc:
            logger.exception("Unexpected error during OAuth exchange")
            return Response({"error": "OAuth exchange failed", "details": str(exc)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        # Subscribe app + register phone using system token if available
        webhook_result = None
        register_result = None
        if portal_config.fb_system_token:
            try:
                webhook_result = subscribe_to_webhooks(waba_id, portal_config.fb_system_token)
                register_result = _register_phone_with_pin(phone_number_id, portal_config.fb_system_token, pin)
            except Exception as exc:
                logger.exception("Post-setup failed (webhook/phone registration)")
                # Continue but surface partial failure

        # Persist IntegrationConfig (multi-instance)
        from portal.integrations.models import IntegrationConfig

        config_defaults = {
            "enabled": True,
            "name": instance_name or phone_number_id,
            "config": {
                "token": access_token,
                "phone_id": phone_number_id,
                "business_account_id": waba_id,
                "url": "https://graph.facebook.com/v21.0/",
                "name": instance_name or verified_name or "",
                "display_phone_number": display_phone_number,
                "verified_name": verified_name,
            },
        }

        integration_cfg, _ = IntegrationConfig.get_or_create_for_tenant(
            tenant=tenant,
            slug="whatsapp",
            instance_id=str(phone_number_id),
            defaults=config_defaults,
        )
        # Update existing config if already present
        integration_cfg.enabled = True
        integration_cfg.name = config_defaults["name"]
        integration_cfg.config.update(config_defaults["config"])
        integration_cfg.save()

        # Optionally sync legacy defaults
        if set_as_default:
            tenant_cfg = TenantConfiguration.objects.filter(tenant=tenant).first()
            if tenant_cfg:
                tenant_cfg.whatsapp_integration_enabled = True
                tenant_cfg.whatsapp_token = access_token
                tenant_cfg.whatsapp_business_account_id = waba_id
                tenant_cfg.whatsapp_phone_id = phone_number_id
                tenant_cfg.whatsapp_name = instance_name or verified_name or ""
                tenant_cfg.whatsapp_url = "https://graph.facebook.com/v21.0/"
                tenant_cfg.save()

        response_data = {
            "status": "ok",
            "instance_id": str(phone_number_id),
            "waba_id": waba_id,
            "phone_number_id": phone_number_id,
            "webhook_subscription": webhook_result,
            "phone_registration": register_result,
        }
        return Response(response_data)


@method_decorator(csrf_exempt, name="dispatch")
class WhatsappEmbeddedSignupCallbackView(IntegrationAPIView):
    """
    OAuth callback for Embedded Signup when Meta redirects with ?code=...
    Primarily provided to satisfy redirect_uri; expects frontend to handle the main POST.
    """

    @extend_schema(
        summary="OAuth callback for WhatsApp Embedded Signup",
        tags=["Integrations", "WhatsApp"],
        responses={200: dict, 400: dict},
    )
    def get(self, request):
        code = request.GET.get("code")
        waba_id = request.GET.get("waba_id")
        phone_number_id = request.GET.get("phone_number_id")

        if not code:
            return Response({"error": "code is required"}, status=status.HTTP_400_BAD_REQUEST)

        # Reuse the POST handler logic by constructing a fake request.data
        request.data = {
            "code": code,
            "waba_id": waba_id,
            "phone_number_id": phone_number_id,
        }
        return self.post(request)


@method_decorator(csrf_exempt, name="dispatch")
class IntegrationConfigListView(IntegrationAPIView):
    """
    List and create integration configurations for a specific type.
    """
    
    @extend_schema(
        summary="List integration configs",
        description="Get all configurations of a specific integration type for the current tenant",
        responses={200: IntegrationConfigSerializer(many=True)},
        tags=["Integrations"],
        examples=[
            OpenApiExample(
                name="WhatsApp configs",
                response_only=True,
                value=[
                    {
                        "id": "550e8400-e29b-41d4-a716-446655440000",
                        "slug": "whatsapp",
                        "instance_id": "sales",
                        "name": "Sales Team",
                        "enabled": True,
                        "config": {
                            "token": "EAAx****1234",
                            "phone_id": "123456789",
                            "business_account_id": "987654321",
                        },
                        "is_configured": True,
                        "integration_name": "WhatsApp Business",
                        "integration_category": "messaging",
                    },
                ],
            ),
        ],
    )
    def get(self, request, slug: str):
        tenant = self.get_tenant()
        if not tenant:
            return Response(
                {"error": "Authentication required"},
                status=status.HTTP_401_UNAUTHORIZED,
            )
        
        if slug not in INTEGRATION_REGISTRY:
            return Response(
                {"error": f"Unknown integration: {slug}"},
                status=status.HTTP_404_NOT_FOUND,
            )
        
        configs = IntegrationConfig.objects.filter(tenant=tenant, slug=slug)
        serializer = IntegrationConfigSerializer(configs, many=True)
        return Response(serializer.data)
    
    @extend_schema(
        summary="Create integration config",
        description="Create a new configuration instance for an integration type",
        request=IntegrationConfigCreateSerializer,
        responses={201: IntegrationConfigSerializer},
        tags=["Integrations"],
        examples=[
            OpenApiExample(
                name="Create WhatsApp config",
                request_only=True,
                value={
                    "instance_id": "support",
                    "name": "Support Team",
                    "enabled": True,
                    "config": {
                        "token": "EAAxxx...",
                        "phone_id": "123456789",
                        "business_account_id": "987654321",
                        "name": "Support Line",
                    },
                },
            ),
        ],
    )
    def post(self, request, slug: str):
        tenant = self.get_tenant()
        if not tenant:
            return Response(
                {"error": "Authentication required"},
                status=status.HTTP_401_UNAUTHORIZED,
            )
        
        definition = get_integration(slug)
        if not definition:
            return Response(
                {"error": f"Unknown integration: {slug}"},
                status=status.HTTP_404_NOT_FOUND,
            )
        
        data = request.data.copy()
        data["slug"] = slug
        
        instance_id = data.get("instance_id", "default")
        if not definition.supports_multi_instance and instance_id != "default":
            return Response(
                {"error": f"{slug} does not support multiple instances"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        
        existing = IntegrationConfig.objects.filter(
            tenant=tenant,
            slug=slug,
            instance_id=instance_id,
        ).first()
        
        if existing:
            return Response(
                {"error": f"Config already exists for {slug}:{instance_id}"},
                status=status.HTTP_409_CONFLICT,
            )
        
        serializer = IntegrationConfigCreateSerializer(
            data=data,
            context={"request": request},
        )
        
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            serializer.save(tenant=tenant)
        except IntegrityError:
            return Response(
                {"error": f"Config already exists for {slug}:{instance_id}"},
                status=status.HTTP_409_CONFLICT,
            )
        return Response(serializer.data, status=status.HTTP_201_CREATED)


@method_decorator(csrf_exempt, name="dispatch")
class IntegrationConfigDetailView(IntegrationAPIView):
    """
    Retrieve, update, or delete a specific integration configuration.
    """
    
    def get_object(self, slug: str, instance_id: str):
        """Get integration config for the current tenant."""
        tenant = self.get_tenant()
        if not tenant:
            return None
        
        return IntegrationConfig.objects.filter(
            tenant=tenant,
            slug=slug,
            instance_id=instance_id,
        ).first()
    
    @extend_schema(
        summary="Get integration config",
        description="Retrieve a specific integration configuration",
        responses={200: IntegrationConfigSerializer},
        tags=["Integrations"],
    )
    def get(self, request, slug: str, instance_id: str = "default"):
        config = self.get_object(slug, instance_id)
        if not config:
            return Response(
                {"error": "Integration config not found"},
                status=status.HTTP_404_NOT_FOUND,
            )
        
        serializer = IntegrationConfigSerializer(config)
        return Response(serializer.data)
    
    @extend_schema(
        summary="Update integration config",
        description="Update an existing integration configuration (partial update)",
        request=IntegrationConfigUpdateSerializer,
        responses={200: IntegrationConfigSerializer},
        tags=["Integrations"],
        examples=[
            OpenApiExample(
                name="Update config",
                request_only=True,
                value={
                    "enabled": True,
                    "config": {
                        "api_key": "sk-new-key...",
                    },
                },
            ),
        ],
    )
    def patch(self, request, slug: str, instance_id: str = "default"):
        config = self.get_object(slug, instance_id)
        if not config:
            return Response(
                {"error": "Integration config not found"},
                status=status.HTTP_404_NOT_FOUND,
            )
        
        serializer = IntegrationConfigUpdateSerializer(
            config,
            data=request.data,
            partial=True,
            context={"request": request},
        )
        
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        
        serializer.save()
        return Response(serializer.data)
    
    @extend_schema(
        summary="Replace integration config",
        description="Fully replace an integration configuration",
        request=IntegrationConfigSerializer,
        responses={200: IntegrationConfigSerializer},
        tags=["Integrations"],
    )
    def put(self, request, slug: str, instance_id: str = "default"):
        config = self.get_object(slug, instance_id)
        if not config:
            return Response(
                {"error": "Integration config not found"},
                status=status.HTTP_404_NOT_FOUND,
            )
        
        data = request.data.copy()
        data["slug"] = slug
        data["instance_id"] = instance_id
        
        serializer = IntegrationConfigSerializer(
            config,
            data=data,
            context={"request": request},
        )
        
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        
        serializer.save()
        return Response(serializer.data)
    
    @extend_schema(
        summary="Delete integration config",
        description="Remove an integration configuration",
        responses={204: None},
        tags=["Integrations"],
    )
    def delete(self, request, slug: str, instance_id: str = "default"):
        config = self.get_object(slug, instance_id)
        if not config:
            return Response(
                {"error": "Integration config not found"},
                status=status.HTTP_404_NOT_FOUND,
            )
        
        config.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


@method_decorator(csrf_exempt, name="dispatch")
class IntegrationCategoriesView(IntegrationAPIView):
    """
    List available integration categories.
    """
    
    @extend_schema(
        summary="List integration categories",
        description="Get all available integration categories",
        responses={200: dict},
        tags=["Integrations"],
        examples=[
            OpenApiExample(
                name="Categories",
                response_only=True,
                value={
                    "categories": ["ai", "messaging", "payments", "logistics", "recruitment", "ecommerce", "cms", "erp", "services"],
                },
            ),
        ],
    )
    def get(self, request):
        return Response({"categories": list_categories()})


@method_decorator(csrf_exempt, name="dispatch")
class IntegrationPublicConfigView(IntegrationAPIView):
    """
    Get public/frontend-safe configuration values for an integration.
    
    Returns ONLY non-sensitive fields that are safe to expose to the browser.
    Use this endpoint to get keys needed for client-side SDKs like:
    - Google Maps JavaScript API browser_key
    - Stripe publishable_key
    - MercadoPago public_key
    """
    
    @extend_schema(
        summary="Get public config",
        description="Get non-sensitive configuration values safe for frontend use",
        responses={200: dict},
        tags=["Integrations"],
        examples=[
            OpenApiExample(
                name="Google public config",
                response_only=True,
                value={
                    "slug": "google",
                    "instance_id": "default",
                    "enabled": True,
                    "public_config": {
                        "browser_key": "AIzaSyBxxxxxxxxxxxxx",
                    },
                },
            ),
        ],
    )
    def get(self, request, slug: str, instance_id: str = "default"):
        tenant = self.get_tenant()
        if not tenant:
            return Response(
                {"error": "Authentication required"},
                status=status.HTTP_401_UNAUTHORIZED,
            )
        
        definition = get_integration(slug)
        if not definition:
            return Response(
                {"error": f"Unknown integration: {slug}"},
                status=status.HTTP_404_NOT_FOUND,
            )
        
        config = IntegrationConfig.objects.filter(
            tenant=tenant,
            slug=slug,
            instance_id=instance_id,
        ).first()
        
        if not config:
            return Response(
                {"error": "Integration config not found"},
                status=status.HTTP_404_NOT_FOUND,
            )
        
        sensitive_fields = get_sensitive_fields(slug)
        public_config = {}
        
        for key, value in config.config.items():
            if key not in sensitive_fields and value:
                public_config[key] = value
        
        return Response({
            "slug": slug,
            "instance_id": instance_id,
            "enabled": config.enabled,
            "public_config": public_config,
        })
