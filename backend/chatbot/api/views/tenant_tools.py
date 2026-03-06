"""API endpoints for tenant tool configuration."""
import logging
from rest_framework import viewsets, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.decorators import action

from chatbot.models.tenant_tool_configuration import TenantToolConfiguration
from chatbot.api.serializers.tenant_tool_config import TenantToolConfigurationSerializer
from portal.context_utils import current_tenant
from resources.api.views import BUILTIN_TOOLS

logger = logging.getLogger(__name__)


def _builtin_tool_list_items():
    """Return tool list items for builtins (same shape as TenantToolConfigurationSerializer output)."""
    return [
        {
            "tool_name": b["name"],
            "tool_type": "builtin",
            "enabled": False,
            "custom_description": "",
            "custom_display_name": b.get("display_name", b["name"]),
            "default_params": {},
            "defaults": {
                "name": b["name"],
                "display_name": b.get("display_name", b["name"]),
                "description": b.get("description", ""),
                "category": "builtin",
                "type": "builtin",
            },
            "created_at": None,
            "updated_at": None,
        }
        for b in BUILTIN_TOOLS
    ]


class TenantToolConfigurationViewSet(viewsets.ModelViewSet):
    """
    ViewSet for managing tenant-level tool configurations.
    
    Endpoints:
    - GET /api/v1/settings/agents/tools/ - List all tool configurations
    - GET /api/v1/settings/agents/tools/{tool_name}/ - Get specific tool configuration
    - PATCH /api/v1/settings/agents/tools/{tool_name}/ - Update tool configuration
    
    Response includes:
    - Current values: tool_name, tool_type, enabled, custom_description, 
      custom_display_name, default_params
    - Defaults (nested object): name, display_name, description, category, 
      type, and optional fields like config_key, requires_vector_store
    """

    serializer_class = TenantToolConfigurationSerializer
    permission_classes = [IsAuthenticated]
    lookup_field = 'tool_name'

    def get_queryset(self):
        tenant = current_tenant.get() or getattr(self.request.user, 'tenant', None)
        if not tenant:
            return TenantToolConfiguration.objects.none()
        
        # Ensure tenant context is set for TenantManager (though we use explicit filter)
        if current_tenant.get() != tenant:
            current_tenant.set(tenant)
        
        return TenantToolConfiguration.objects.filter(tenant=tenant).order_by('tool_name')

    def list(self, request, *args, **kwargs):
        """List all tool configurations for the tenant, including builtin tools (e.g. Code Interpreter).

        Response is a JSON array. Each item has tool_name, tool_type, enabled, defaults, etc.
        Builtins (web_search, file_search, code_interpreter, image_generation) are always
        appended so Automation Studio and other clients can show and toggle them.
        """
        try:
            response = super().list(request, *args, **kwargs)
            if response.data is None:
                response.data = []

            # Support both raw list and paginated {"results": [...]}
            if isinstance(response.data, list):
                items = response.data
                existing_names = {item.get("tool_name") for item in items if isinstance(item, dict)}
                extra = [item for item in _builtin_tool_list_items() if item["tool_name"] not in existing_names]
                if extra:
                    response.data = list(items) + extra
            else:
                if not isinstance(response.data, dict):
                    return response
                response.data = dict(response.data)
                results = response.data.get("results")
                if isinstance(results, list):
                    existing_names = {item.get("tool_name") for item in results if isinstance(item, dict)}
                    extra = [item for item in _builtin_tool_list_items() if item["tool_name"] not in existing_names]
                    if extra:
                        response.data["results"] = list(results) + extra
            return response
        except Exception as e:
            logger.error(f"Error listing tenant tools: {e}")
            return Response(
                {"error": "Failed to list tool configurations"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    def retrieve(self, request, *args, **kwargs):
        """Get a specific tool configuration."""
        try:
            return super().retrieve(request, *args, **kwargs)
        except TenantToolConfiguration.DoesNotExist:
            return Response(
                {"error": "Tool not found"},
                status=status.HTTP_404_NOT_FOUND
            )
        except Exception as e:
            logger.error(f"Error retrieving tenant tool: {e}")
            return Response(
                {"error": "Failed to retrieve tool configuration"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    def partial_update(self, request, *args, **kwargs):
        """Update tool customizations."""
        try:
            return super().partial_update(request, *args, **kwargs)
        except Exception as e:
            logger.error(f"Error updating tenant tool: {e}")
            return Response(
                {"error": "Failed to update tool configuration"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
