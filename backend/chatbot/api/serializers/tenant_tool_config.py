"""Serializers for TenantToolConfiguration."""
from rest_framework import serializers
from chatbot.models.tenant_tool_configuration import TenantToolConfiguration
from chatbot.agents.moio_agents_loader import get_available_tools
from resources.api.views import TOOL_CATEGORIES, ToolCategory


class TenantToolConfigurationSerializer(serializers.ModelSerializer):
    """Serializer with embedded defaults for comparison/reset."""
    
    defaults = serializers.SerializerMethodField()

    class Meta:
        model = TenantToolConfiguration
        fields = (
            'tool_name',
            'tool_type',
            'enabled',
            'custom_description',
            'custom_display_name',
            'default_params',
            'defaults',
            'created_at',
            'updated_at',
        )
        read_only_fields = ('tool_name', 'tool_type', 'created_at', 'updated_at')

    def get_defaults(self, obj) -> dict:
        """Fetch original tool definition for comparison using get_available_tools().
        
        Returns default values from the FunctionTool object including:
        - name, display_name, description
        - category, type
        
        Note: Builtin tools are not handled here as they are not returned by get_available_tools().
        params_json_schema is excluded as it's for tool output handling, not user customization.
        """
        try:
            # Get all available tools from moio_agents_loader
            # This returns a list of FunctionTool objects (custom tools only)
            available_tools = get_available_tools()
            
            # Find the tool by name
            original_tool = next(
                (tool for tool in available_tools if tool.name == obj.tool_name),
                None
            )
            
            if original_tool:
                # Extract information from FunctionTool object
                # Only include fields that users can customize
                defaults = {
                    'name': original_tool.name or '',
                    'display_name': original_tool.name.replace('_', ' ').title() if original_tool.name else '',
                    'description': original_tool.description or '',
                    'category': TOOL_CATEGORIES.get(original_tool.name, ToolCategory.CUSTOM),
                    'type': 'custom',  # All tools from get_available_tools() are custom FunctionTools
                }
                
                return defaults
            
            # Return empty defaults structure if tool not found
            return {
                'name': '',
                'display_name': '',
                'description': '',
                'category': '',
                'type': '',
            }
        except Exception:
            # On any error, return empty defaults structure
            return {
                'name': '',
                'display_name': '',
                'description': '',
                'category': '',
                'type': '',
            }
