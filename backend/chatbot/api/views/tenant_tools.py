"""API endpoints for tenant tool configuration."""
import logging
from rest_framework import viewsets, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from chatbot.agents.moio_agents_loader import get_available_tools
from chatbot.models.tenant_tool_configuration import TenantToolConfiguration
from chatbot.api.serializers.tenant_tool_config import TenantToolConfigurationSerializer
from central_hub.context_utils import current_tenant
from resources.api.views import BUILTIN_TOOLS, TOOL_CATEGORIES, ToolCategory
from tenancy.resolution import activate_tenant

logger = logging.getLogger(__name__)


def _set_connection_tenant(tenant) -> None:
    try:
        activate_tenant(tenant)
    except Exception as exc:
        logger.warning("Unable to switch DB tenant schema to %s: %s", tenant.schema_name, exc)


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


def _custom_tool_list_items():
    """Return tool list items derived from the runtime tool repository."""
    items = []
    for tool in get_available_tools():
        tool_name = tool.name
        items.append(
            {
                "tool_name": tool_name,
                "tool_type": "custom",
                "enabled": getattr(tool, "is_enabled", True),
                "custom_description": tool.description or "",
                "custom_display_name": tool_name.replace("_", " ").title(),
                "default_params": tool.params_json_schema or {},
                "defaults": {
                    "name": tool_name,
                    "display_name": tool_name.replace("_", " ").title(),
                    "description": tool.description or "",
                    "category": TOOL_CATEGORIES.get(tool_name, ToolCategory.CUSTOM),
                    "type": "custom",
                },
                "created_at": None,
                "updated_at": None,
            }
        )
    return items


def _merge_tool_overrides(base_item, override_item):
    """Merge persisted tenant overrides on top of runtime-derived defaults."""
    merged = dict(base_item)
    for key in (
        "enabled",
        "custom_description",
        "custom_display_name",
        "default_params",
        "created_at",
        "updated_at",
    ):
        if key in override_item:
            merged[key] = override_item[key]
    return merged


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
        _set_connection_tenant(tenant)

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
                response.data = self._merge_available_tools(list(response.data))
            else:
                if not isinstance(response.data, dict):
                    return response
                response.data = dict(response.data)
                results = response.data.get("results")
                if isinstance(results, list):
                    response.data["results"] = self._merge_available_tools(list(results))
            return response
        except Exception as e:
            logger.error(f"Error listing tenant tools: {e}")
            # Degrade gracefully so settings screens can still render repo tools and builtins.
            fallback_items = _custom_tool_list_items() + _builtin_tool_list_items()
            fallback_items.sort(key=lambda item: item["tool_name"])
            return Response(fallback_items, status=status.HTTP_200_OK)

    def _merge_available_tools(self, persisted_items):
        """Return runtime-derived tools with tenant overrides applied."""
        runtime_items = {
            item["tool_name"]: item
            for item in (_custom_tool_list_items() + _builtin_tool_list_items())
        }
        merged_items = {}

        for name, runtime_item in runtime_items.items():
            merged_items[name] = dict(runtime_item)

        for item in persisted_items:
            if not isinstance(item, dict):
                continue

            tool_name = item.get("tool_name")
            if not tool_name:
                continue

            runtime_item = runtime_items.get(tool_name)
            if runtime_item is not None:
                merged_items[tool_name] = _merge_tool_overrides(runtime_item, item)
            else:
                merged_items[tool_name] = item

        return sorted(merged_items.values(), key=lambda item: item["tool_name"])

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
