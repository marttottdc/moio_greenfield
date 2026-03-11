from __future__ import annotations

import json
import logging
from typing import Any, Dict, Optional, Type


from django.db import IntegrityError
from django.http import Http404
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.exceptions import ValidationError

from crm.models import WebhookConfig
from crm.services.agent_service import AgentService
from central_hub.tenant_config import get_tenant_config

from .config_persistence import (
    persist_integration_config,
    persist_org_settings,
    disable_integration,
)
from .serializers import (
    AgentConfigurationSerializer,
    INTEGRATION_SERIALIZERS,
    WebhookConfigSerializer,
    BaseConfigSerializer,
    PreferenceUpdateSerializer,
    LocalizationUpdateSerializer,
    LocationUpdateSerializer,
)
from .preferences import build_user_preferences, update_user_preferences, update_user_location

logger = logging.getLogger(__name__)


SUPPORTED_INTEGRATIONS = {
    "whatsapp": {
        "name": "WhatsApp Business",
        "description": "Customer messaging and support",
        "serializer": "whatsapp",
        "enabled_field": "whatsapp_integration_enabled",
    },
    "openai": {
        "name": "OpenAI",
        "description": "AI-powered assistance and automation",
        "serializer": "openai",
        "enabled_field": "openai_integration_enabled",
    },
    "gmail": {
        "name": "Gmail",
        "description": "Email communication and automation",
        "serializer": "smtp",
        "enabled_field": "smtp_integration_enabled",
    },
    "mercadopago": {
        "name": "Mercado Pago",
        "description": "Payment collection and billing",
        "serializer": "mercadopago",
        "enabled_field": "mercadopago_integration_enabled",
    },
}


class TenantConfigurationViewSet(viewsets.GenericViewSet):
    """GET/PATCH per-integration settings. Reads via get_tenant_config; writes via IntegrationConfig/Tenant."""
    permission_classes = [IsAuthenticated]
    lookup_field = "integration"
    lookup_url_kwarg = "integration"

    def get_serializer_class(self) -> Type[BaseConfigSerializer]:
        slug = self.kwargs.get(self.lookup_url_kwarg)
        serializer_class = INTEGRATION_SERIALIZERS.get(slug)
        if not serializer_class:
            raise Http404("Integration not supported")
        return serializer_class

    def _get_tenant(self):
        tenant = getattr(self.request.user, "tenant", None)
        if tenant is None:
            raise Http404
        return tenant

    def get_object(self):
        """Return config object from get_tenant_config (SimpleNamespace)."""
        tenant = self._get_tenant()
        return get_tenant_config(tenant)

    def retrieve(self, request, *args, **kwargs) -> Response:
        config = self.get_object()
        serializer = self.get_serializer(config)
        return Response(serializer.data)

    def partial_update(self, request, *args, **kwargs) -> Response:
        tenant = self._get_tenant()
        integration_slug = self.kwargs.get(self.lookup_url_kwarg)
        serializer = self.get_serializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        validated_data = serializer.validated_data

        if integration_slug == "assistants":
            persist_org_settings(tenant, validated_data)
        else:
            persist_integration_config(tenant, integration_slug, validated_data)

        config = get_tenant_config(tenant)
        output = self.get_serializer(config)
        return Response(output.data)


class AgentConfigurationViewSet(viewsets.ViewSet):
    permission_classes = [IsAuthenticated]
    serializer_class = AgentConfigurationSerializer

    def get_tenant(self):
        tenant = getattr(self.request.user, "tenant", None)
        if tenant is None:
            logger.warning(f"User {self.request.user.id} has no tenant assigned")
            raise Http404
        logger.debug(f"Retrieved tenant {tenant.id} ({tenant}) for user {self.request.user.id}")
        return tenant

    def _ensure_tenant_context(self, tenant):
        """Ensure tenant context is set for TenantManager filtering."""
        from central_hub.context_utils import current_tenant
        context_tenant = current_tenant.get()
        if context_tenant != tenant:
            logger.debug(f"Setting tenant context: {tenant.id} (was: {context_tenant})")
            current_tenant.set(tenant)

    def get_serializer(self, *args, **kwargs):
        kwargs.setdefault("context", self.get_serializer_context())
        return self.serializer_class(*args, **kwargs)

    def get_serializer_context(self) -> Dict[str, Any]:
        return {"request": self.request}

    def _serialize_tools(self, tools: Optional[Any]) -> str:
        if tools is None:
            return "{}"
        return json.dumps(tools)

    def list(self, request) -> Response:
        logger.info(f"AgentConfigurationViewSet.list() called for user {request.user.id}")
        tenant = self.get_tenant()
        logger.info(f"Tenant from request.user: {tenant.id} ({tenant})")
        self._ensure_tenant_context(tenant)
        
        agents = AgentService.list_agents(tenant)
        logger.info(f"Found {len(agents)} agents for tenant {tenant.id}")
        serializer = self.get_serializer(agents, many=True)
        logger.debug(f"Returning {len(serializer.data)} serialized agents")
        return Response(serializer.data)

    def retrieve(self, request, pk=None) -> Response:
        tenant = self.get_tenant()
        self._ensure_tenant_context(tenant)
        agent = AgentService.get_agent_by_id(pk, tenant)
        if not agent:
            raise Http404
        serializer = self.get_serializer(agent)
        return Response(serializer.data)

    def create(self, request) -> Response:
        tenant = self.get_tenant()
        self._ensure_tenant_context(tenant)
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            agent = serializer.save(tenant=tenant)
        except IntegrityError as e:
            raise ValidationError({"non_field_errors": [str(e)]})

        output = self.get_serializer(agent)
        return Response(output.data, status=status.HTTP_201_CREATED)

    def update(self, request, pk=None) -> Response:
        return self._update(request, pk, partial=False)

    def partial_update(self, request, pk=None) -> Response:
        return self._update(request, pk, partial=True)

    def _update(self, request, pk: str, partial: bool) -> Response:
        tenant = self.get_tenant()
        self._ensure_tenant_context(tenant)
        agent = AgentService.get_agent_by_id(pk, tenant)
        if not agent:
            raise Http404

        serializer = self.get_serializer(agent, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        try:
            agent = serializer.save()
        except IntegrityError as e:
            raise ValidationError({"non_field_errors": [str(e)]})

        agent.refresh_from_db()
        output = self.get_serializer(agent)
        return Response(output.data)

    def destroy(self, request, pk=None) -> Response:
        tenant = self.get_tenant()
        self._ensure_tenant_context(tenant)
        success, message = AgentService.delete_agent(pk, tenant)
        if not success:
            if "not found" in message.lower():
                raise Http404
            raise ValidationError({"non_field_errors": [message]})
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=False, methods=["get"], url_path="channels")
    def channels(self, request) -> Response:
        """Get available channel choices for agent configuration."""
        from chatbot.models.agent_configuration import CHANNEL_CHOICES
        
        channels = [
            {"value": value, "label": label}
            for value, label in CHANNEL_CHOICES
        ]
        
        return Response({"channels": channels})


class WebhookConfigViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated]
    serializer_class = WebhookConfigSerializer
    queryset = WebhookConfig.objects.all()

    def get_queryset(self):
        tenant = getattr(self.request.user, "tenant", None)
        if not tenant:
            return WebhookConfig.objects.none()
        return super().get_queryset().filter(tenant=tenant)

    def perform_create(self, serializer):
        tenant = getattr(self.request.user, "tenant", None)
        if tenant is None:
            raise Http404
        serializer.save(tenant=tenant)

    @action(detail=False, methods=["get"], url_path="handlers")
    def handlers(self, request):
        from central_hub.webhooks.registry import get_available_handlers
        handlers = get_available_handlers()
        return Response({"handlers": handlers})


class IntegrationViewSet(viewsets.ViewSet):
    """List/retrieve integrations; connect/disconnect via IntegrationConfig API."""
    permission_classes = [IsAuthenticated]

    def _get_tenant(self):
        tenant = getattr(self.request.user, "tenant", None)
        if tenant is None:
            raise Http404
        return tenant

    def _get_config(self):
        tenant = self._get_tenant()
        return get_tenant_config(tenant)

    def _get_meta(self, slug: str) -> dict:
        meta = SUPPORTED_INTEGRATIONS.get(slug)
        if not meta:
            raise Http404("Integration not supported")
        return meta

    def _get_serializer_class(self, slug: str):
        meta = self._get_meta(slug)
        serializer_slug = meta["serializer"]
        serializer_class = INTEGRATION_SERIALIZERS.get(serializer_slug)
        if not serializer_class:
            raise Http404("Integration serializer not found")
        return serializer_class

    def _integration_payload(self, slug: str, config) -> dict:
        meta = self._get_meta(slug)
        serializer_class = self._get_serializer_class(slug)
        enabled = getattr(config, meta["enabled_field"], False)
        serializer = serializer_class(config)
        
        payload = {
            "id": slug,
            "name": meta["name"],
            "description": meta["description"],
            "connected": enabled,
            "config": serializer.data if enabled else None,
            "last_sync": None,
        }
        
        # For OpenAI, fetch available models
        if slug == "openai" and enabled and getattr(config, "openai_api_key", None):
            try:
                from openai import OpenAI
                client = OpenAI(api_key=config.openai_api_key)
                models_response = client.models.list()
                payload["available_models"] = [
                    {"id": model.id, "created": model.created}
                    for model in models_response.data
                ]
            except Exception as e:
                logger.warning(f"Failed to fetch OpenAI models: {str(e)}")
                payload["available_models"] = []
        
        return payload

    def list(self, request) -> Response:
        config = self._get_config()
        data = [self._integration_payload(slug, config) for slug in SUPPORTED_INTEGRATIONS]
        return Response({"integrations": data})

    def retrieve(self, request, pk=None) -> Response:
        config = self._get_config()
        try:
            payload = self._integration_payload(pk, config)
        except Http404:
            raise
        return Response(payload)

    def destroy(self, request, pk=None) -> Response:
        tenant = self._get_tenant()
        disable_integration(tenant, pk)
        return Response({"message": "Integration disconnected successfully"})

    @action(detail=True, methods=["post"], url_path="connect")
    def connect(self, request, pk=None) -> Response:
        tenant = self._get_tenant()
        meta = self._get_meta(pk)
        serializer_class = self._get_serializer_class(pk)
        serializer = serializer_class(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        validated_data = dict(serializer.validated_data)
        validated_data[meta["enabled_field"]] = True
        persist_integration_config(tenant, pk, validated_data, enabled=True)

        config = get_tenant_config(tenant)
        payload = self._integration_payload(pk, config)
        payload["message"] = "Integration connected successfully"
        return Response(payload)


class PreferencesViewSet(viewsets.ViewSet):
    permission_classes = [IsAuthenticated]
    serializer_class = PreferenceUpdateSerializer

    def _get_config(self):
        tenant = getattr(self.request.user, "tenant", None)
        if not tenant:
            return None
        return get_tenant_config(tenant)

    def _system_settings(self, config) -> dict:
        tenant = getattr(self.request.user, "tenant", None)
        return {
            "organization_name": tenant.nombre if tenant else "",
            "currency": getattr(config, "organization_currency", "USD") if config else "USD",
            "date_format": getattr(config, "organization_date_format", "DD/MM/YYYY") if config else "DD/MM/YYYY",
            "time_format": getattr(config, "organization_time_format", "24h") if config else "24h",
            "timezone": getattr(config, "organization_timezone", "UTC") if config else "UTC",
        }

    def retrieve(self, request, *args, **kwargs) -> Response:
        config = self._get_config()
        preferences = build_user_preferences(request.user, config)
        return Response(
            {
                "user_preferences": preferences,
                "system_settings": self._system_settings(config),
            }
        )

    def partial_update(self, request, *args, **kwargs) -> Response:
        serializer = self.serializer_class(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        config = self._get_config()
        updated = update_user_preferences(request.user, config, serializer.validated_data)
        return Response({"message": "Preferences updated successfully", "preferences": updated})

    def perform_update(self, serializer):
        tenant = getattr(self.request.user, "tenant", None)
        if tenant is None:
            raise Http404
        serializer.save(tenant=tenant)


class LocalizationViewSet(viewsets.ViewSet):
    """GET/PATCH /api/v1/settings/localization/ — language, timezone, currency (tenant defaults + user override)."""
    permission_classes = [IsAuthenticated]
    serializer_class = LocalizationUpdateSerializer

    def _get_config(self):
        tenant = getattr(self.request.user, "tenant", None)
        if not tenant:
            return None
        return get_tenant_config(tenant)

    def retrieve(self, request, *args, **kwargs) -> Response:
        config = self._get_config()
        prefs = build_user_preferences(request.user, config)
        return Response({
            "language": prefs.get("language", "en"),
            "timezone": prefs.get("timezone", "UTC"),
            "currency": prefs.get("currency", "USD"),
            "system_defaults": {
                "language": getattr(config, "organization_locale", None) or "en" if config else "en",
                "timezone": getattr(config, "organization_timezone", None) or "UTC" if config else "UTC",
                "currency": getattr(config, "organization_currency", None) or "USD" if config else "USD",
            },
        })

    def partial_update(self, request, *args, **kwargs) -> Response:
        serializer = self.serializer_class(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        config = self._get_config()
        updated = update_user_preferences(request.user, config, serializer.validated_data)
        return Response({
            "message": "Localization preferences updated",
            "language": updated.get("language", "en"),
            "timezone": updated.get("timezone", "UTC"),
            "currency": updated.get("currency", "USD"),
        })


class LocationViewSet(viewsets.ViewSet):
    """GET/PATCH /api/v1/settings/location/ — last_location guardada cada ~5 min para usar en actividades."""
    permission_classes = [IsAuthenticated]
    serializer_class = LocationUpdateSerializer

    def retrieve(self, request, *args, **kwargs) -> Response:
        prefs = build_user_preferences(request.user, None)
        return Response({
            "last_location": prefs.get("last_location") or None,
            "last_location_updated_at": prefs.get("last_location_updated_at") or None,
        })

    def partial_update(self, request, *args, **kwargs) -> Response:
        serializer = self.serializer_class(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        result = update_user_location(request.user, serializer.validated_data["address"])
        return Response(result)
