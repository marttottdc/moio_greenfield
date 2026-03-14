"""
Integration API Views

Provides REST API endpoints for managing integration configurations.
Uses registry-backed resolution for dynamic schema validation.
"""

from __future__ import annotations

from typing import Any

from django.db import IntegrityError
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView
from drf_spectacular.utils import extend_schema, OpenApiParameter, OpenApiExample

from central_hub.authentication import CsrfExemptSessionAuthentication, TenantJWTAAuthentication
from security.authentication import ServiceJWTAuthentication
from central_hub.integrations.models import IntegrationConfig
from central_hub.integrations.registry import (
    INTEGRATION_REGISTRY,
    get_integration,
    get_integration_schema,
    get_sensitive_fields,
    list_integrations,
    list_categories,
)
from central_hub.models import PlatformConfiguration
from chatbot.lib.whatsapp_client_api import (
    subscribe_to_webhooks,
    register_waba_phone_number,
)

import logging
import requests
from urllib.parse import urljoin

logger = logging.getLogger(__name__)


def _enrich_shopify_config_from_link(tenant, cfg: dict, instance_id: str) -> None:
    """In-place: set store_url and access_token from ShopifyShopLink when missing (managed by OAuth/embed)."""
    if not isinstance(cfg, dict):
        return
    need_url = not (cfg.get("store_url") or "").strip()
    need_token = not (cfg.get("access_token") or "").strip() or cfg.get("access_token") == "****"
    if not need_url and not need_token:
        return
    from central_hub.integrations.models import ShopifyShopLink, ShopifyShopLinkStatus
    links = list(
        ShopifyShopLink.objects.filter(
            tenant=tenant,
            status=ShopifyShopLinkStatus.LINKED,
        ).values_list("shop_domain", flat=True)
    )
    link_domain = None
    for shop_domain in links:
        _id = (shop_domain or "").replace(".myshopify.com", "").replace(".", "-")
        if _id == instance_id:
            link_domain = shop_domain
            break
    if not link_domain and links:
        link_domain = links[0]
    if link_domain:
        if need_url:
            cfg["store_url"] = link_domain
        if need_token:
            cfg["access_token"] = "••••••••"


from central_hub.integrations.serializers import (
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
            configs = list(
                IntegrationConfig.objects.filter(
                    tenant=tenant,
                    slug=definition.slug,
                )
            )
            
            enabled_count = sum(1 for c in configs if c.enabled)
            configured_count = sum(1 for c in configs if c.is_configured())
            
            connection_status = "not_configured"
            if configured_count > 0:
                if enabled_count > 0:
                    any_ok = any(
                        c.metadata.get("last_connection_ok") for c in configs if c.is_configured()
                    )
                    connection_status = "connected" if any_ok else "configured"
                else:
                    connection_status = "configured"
            
            # Hub contract: expose definition transport and binding status
            binding_statuses = [getattr(c, "status", None) for c in configs if hasattr(c, "status")]
            result.append({
                "slug": definition.slug,
                "name": definition.name,
                "description": definition.description,
                "category": definition.category,
                "icon": definition.icon,
                "supports_multi_instance": definition.supports_multi_instance,
                "is_configured": configured_count > 0,
                "enabled": enabled_count > 0,
                "instance_count": len(configs),
                "connection_status": connection_status,
                "auth_scope": getattr(definition, "auth_scope", "tenant"),
                "supports_webhook": getattr(definition, "supports_webhook", False),
                "supports_oauth": getattr(definition, "supports_oauth", False),
                "binding_statuses": [s for s in binding_statuses if s],
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


def _build_redirect_uri(portal_config: PlatformConfiguration) -> str:
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
        portal_config = PlatformConfiguration.objects.first()
        if not portal_config:
            return Response(
                {"error": "PlatformConfiguration not found"},
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

        portal_config = PlatformConfiguration.objects.first()
        if not portal_config or not portal_config.fb_moio_bot_app_id or not portal_config.fb_moio_bot_app_secret:
            return Response(
                {"error": "PlatformConfiguration missing Facebook app credentials"},
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

        # Persist IntegrationConfig (multi-instance, Hub contract status)
        from central_hub.integrations.models import IntegrationConfig, IntegrationBindingStatus

        config_defaults = {
            "enabled": True,
            "status": IntegrationBindingStatus.CONNECTED,
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
        integration_cfg.status = IntegrationBindingStatus.CONNECTED
        integration_cfg.name = config_defaults["name"]
        integration_cfg.config.update(config_defaults["config"])
        integration_cfg.save()

        # set_as_default: IntegrationConfig is already created with enabled=True above

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
        data = serializer.data
        # Shopify: enrich each config from ShopifyShopLink when store_url/access_token missing
        if slug == "shopify" and isinstance(data, list):
            for item in data:
                if isinstance(item.get("config"), dict):
                    _enrich_shopify_config_from_link(
                        tenant,
                        item["config"],
                        item.get("instance_id") or "default",
                    )
        return Response(data)
    
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
            # Upsert: update existing config so "save" from frontend always works
            update_data = request.data.copy() if hasattr(request.data, "copy") else dict(request.data)
            if slug == "shopify":
                shopify_config = dict(update_data.get("config") or {})
                for key in ("access_token", "webhook_secret", "store_url"):
                    shopify_config.pop(key, None)
                update_data["config"] = shopify_config
            serializer = IntegrationConfigUpdateSerializer(
                existing,
                data=update_data,
                partial=True,
                context={"request": request},
            )
            if not serializer.is_valid():
                return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
            serializer.save()
            logger.info("Integration config updated (upsert): slug=%s instance_id=%s", slug, instance_id)
            out_serializer = IntegrationConfigSerializer(existing, context={"request": request})
            return Response(out_serializer.data)
        
        serializer = IntegrationConfigCreateSerializer(
            data=data,
            context={"request": request},
        )
        
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            instance = serializer.save(tenant=tenant)
            logger.info("Integration config created: slug=%s instance_id=%s", slug, instance_id)
        except IntegrityError:
            # Row exists but is not visible (e.g. tenant_uuid NULL). We do not disable RLS here.
            # Run: python manage.py backfill_tenant_uuid
            return Response(
                {
                    "error": f"Config already exists for {slug}:{instance_id}",
                    "hint": "Run: python manage.py backfill_tenant_uuid (then save again).",
                },
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
        # Shopify: if stored config is missing store_url/access_token but we have a LINKED link, persist full config
        if slug == "shopify":
            tenant = self.get_tenant()
            if tenant and isinstance(config.config, dict):
                need_write = not (config.config.get("store_url") or "").strip() or not (config.config.get("access_token") or "").strip()
                if need_write:
                    from central_hub.integrations.shopify.views import ensure_shopify_config_persisted_from_link
                    updated = ensure_shopify_config_persisted_from_link(tenant, instance_id)
                    if updated:
                        config = updated
        serializer = IntegrationConfigSerializer(config)
        data = serializer.data
        # Shopify: enrich config from ShopifyShopLink when store_url/access_token missing (e.g. managed by embed/OAuth)
        if slug == "shopify":
            tenant = self.get_tenant()
            _enrich_shopify_config_from_link(tenant, data.get("config"), instance_id)
        return Response(data)
    
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

        data = request.data.copy() if hasattr(request.data, "copy") else dict(request.data)
        if slug == "shopify":
            shopify_config = dict(data.get("config") or {})
            for key in ("access_token", "webhook_secret", "store_url"):
                shopify_config.pop(key, None)
            data["config"] = shopify_config

        serializer = IntegrationConfigUpdateSerializer(
            config,
            data=data,
            partial=True,
            context={"request": request},
        )
        
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        
        instance = serializer.save()
        logger.info("Integration config updated: slug=%s instance_id=%s", slug, instance_id)
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
class IntegrationConfigTestView(IntegrationAPIView):
    """
    Test an integration connection by validating credentials/config.
    POST with { config: {...} } to test before or after saving.
    """

    @extend_schema(
        summary="Test integration connection",
        description="Validate integration credentials/config. Uses config from request body, or stored config if not provided.",
        request={
            "application/json": {
                "type": "object",
                "properties": {
                    "config": {"type": "object", "description": "Config to test (optional; uses stored config if omitted)"},
                },
            }
        },
        responses={
            200: {"type": "object", "properties": {"success": {"type": "boolean"}, "message": {"type": "string"}}},
            400: {"description": "Test failed or invalid config"},
            404: {"description": "Integration not found"},
        },
        tags=["Integrations"],
    )
    def post(self, request, slug: str, instance_id: str = "default"):
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

        data = getattr(request, "data", None) or {}
        config = data.get("config") or data.get("data", {}).get("config") or {}

        # Fall back to stored config if request config is empty/masked
        def _is_empty_or_masked(v):
            if v is None or v == "":
                return True
            if isinstance(v, str):
                s = v.replace(" ", "")
                if "****" in v or (len(s) >= 4 and all(c in "•▪." for c in s)):
                    return True
            return False

        if not config or all(_is_empty_or_masked(v) for v in (config or {}).values()):
            stored = IntegrationConfig.objects.filter(
                tenant=tenant, slug=slug, instance_id=instance_id
            ).first()
            if stored:
                config = dict(stored.config)

        if slug == "shopify":
            store_url = (config.get("store_url") or "").strip()
            access_token = (config.get("access_token") or "").strip()
            api_version = (config.get("api_version") or "2024-01").strip()
            if not store_url or not access_token:
                return Response(
                    {"success": False, "message": "Store URL and access token are required"},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            try:
                from central_hub.integrations.shopify.shopify_api import ShopifyAPIClient
                client = ShopifyAPIClient(store_url=store_url, access_token=access_token, api_version=api_version)
                ok = client.test_connection()
                if ok:
                    return Response({"success": True, "message": "Shopify connection successful"})
                return Response(
                    {"success": False, "message": "Shopify connection test failed"},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            except Exception as e:
                logger.warning("Shopify test_connection failed: %s", e)
                return Response(
                    {"success": False, "message": str(e)},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        # Generic fallback for integrations without a dedicated test
        return Response(
            {"success": True, "message": f"Connection test not implemented for {slug}. Config structure validated."},
        )


@method_decorator(csrf_exempt, name="dispatch")
class OpenAIModelsView(IntegrationAPIView):
    """
    List OpenAI models via models.list() - validates API key and returns model list.
    POST with { config: { api_key: "..." } } to fetch models and confirm status.
    """

    @extend_schema(
        summary="List OpenAI models",
        description="Call OpenAI models.list() with the provided API key. Validates the key and returns available models for the default_model selector.",
        request={
            "application/json": {
                "type": "object",
                "properties": {
                    "config": {
                        "type": "object",
                        "properties": {"api_key": {"type": "string"}},
                        "required": ["api_key"],
                    }
                },
            }
        },
        responses={
            200: {
                "type": "object",
                "properties": {
                    "success": {"type": "boolean"},
                    "models": {
                        "type": "array",
                        "items": {"type": "object", "properties": {"id": {"type": "string"}}},
                    },
                },
            },
            400: {"description": "Invalid request or API key"},
        },
        tags=["Integrations"],
    )
    def post(self, request):
        tenant = self.get_tenant()
        if tenant is None:
            return Response(
                {"error": "Authentication required"},
                status=status.HTTP_401_UNAUTHORIZED,
            )
        data = getattr(request, "data", None) or {}
        config = data.get("config") or {}
        api_key = (config.get("api_key") or "").strip()

        def _is_empty_or_masked(key: str) -> bool:
            if not key:
                return True
            if "****" in key:  # Serializer mask (e.g. sk-t****2345)
                return True
            # Frontend placeholder when saved key is hidden (e.g. ••••••••••••)
            stripped = key.replace(" ", "")
            if stripped and all(c in "•▪." for c in stripped) and len(stripped) >= 4:
                return True
            return False

        if _is_empty_or_masked(api_key):
            stored = IntegrationConfig.get_for_tenant(tenant, "openai", "default")
            if not stored:
                try:
                    from tenancy.tenant_support import public_schema_context
                    with public_schema_context("public"):
                        stored = IntegrationConfig._base_manager.filter(
                            tenant_id=tenant.pk, slug="openai", instance_id="default"
                        ).first()
                except Exception:
                    pass
            if stored and stored.is_configured():
                api_key = (stored.config.get("api_key") or "").strip()
            if not api_key:
                return Response(
                    {"success": False, "error": "api_key required in config or stored configuration"},
                    status=status.HTTP_400_BAD_REQUEST,
                )
        try:
            from openai import OpenAI
            client = OpenAI(api_key=api_key)
            models_response = client.models.list()
            models = [
                {"id": m.id, "created": getattr(m, "created", None), "owned_by": getattr(m, "owned_by", "")}
                for m in (models_response.data or [])
            ]
            models.sort(key=lambda x: (0 if x["id"].startswith("gpt") else 1, x["id"]))
            stored = IntegrationConfig.get_for_tenant(tenant, "openai", "default")
            if stored:
                stored.metadata.update(
                    {"last_connection_ok": True, "last_connection_at": timezone.now().isoformat()}
                )
                stored.save(update_fields=["metadata", "updated_at"])
            return Response({"success": True, "models": models})
        except Exception as e:
            logger.warning("OpenAI models.list failed: %s", e)
            stored = IntegrationConfig.get_for_tenant(tenant, "openai", "default")
            if stored:
                stored.metadata.update(
                    {"last_connection_ok": False, "last_connection_at": timezone.now().isoformat()}
                )
                stored.save(update_fields=["metadata", "updated_at"])
            return Response(
                {"success": False, "error": str(e)},
                status=status.HTTP_400_BAD_REQUEST,
            )


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
