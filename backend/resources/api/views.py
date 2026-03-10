"""Shared resource endpoints exposed under /api/v1/resources."""

from __future__ import annotations

from django.db.models import Q
from drf_spectacular.utils import OpenApiExample, OpenApiResponse, extend_schema
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from resources.api.serializers import (
    WhatsappTemplateDetailResponseSerializer,
    WhatsappTemplateListResponseSerializer,
    WhatsappTemplateTestResponseSerializer,
    WhatsappTemplateTestSerializer,
)
from chatbot.lib.whatsapp_client_api import (
    WhatsappBusinessClient,
    compose_template_based_message,
    replace_template_placeholders,
    template_requirements,
)
from crm.models import Contact
from central_hub.context_utils import current_tenant
from central_hub.models import TenantConfiguration


class ContactSearchView(APIView):
    """Tenant-scoped search for CRM contacts."""

    permission_classes = [IsAuthenticated]

    @staticmethod
    def _get_tenant(request):
        return current_tenant.get() or getattr(getattr(request, "user", None), "tenant", None)

    def get(self, request):
        tenant = self._get_tenant(request)
        if tenant is None:
            return Response({"results": []}, status=status.HTTP_403_FORBIDDEN)
        query = request.query_params.get("q", "").strip()
        if len(query) < 2:
            return Response({"results": []})

        contacts = (
            Contact.objects.filter(tenant=tenant)
            .filter(
                Q(fullname__icontains=query)
                | Q(email__icontains=query)
                | Q(phone__icontains=query)
            )[:20]
        )
        results = [
            {
                "id": str(contact.pk),
                "fullname": contact.fullname,
                "email": contact.email,
                "phone": contact.phone,
            }
            for contact in contacts
        ]
        return Response({"results": results})


class WhatsappTemplateViewSet(viewsets.ViewSet):
    """Expose WhatsApp message templates available to the tenant."""

    permission_classes = [IsAuthenticated]

    @staticmethod
    def _get_tenant(request):
        return current_tenant.get() or getattr(getattr(request, "user", None), "tenant", None)

    @extend_schema(
        tags=["WhatsApp Templates"],
        summary="List WhatsApp templates for the tenant",
        description=(
            "Retrieves all WhatsApp message templates downloaded from Meta for the current "
            "tenant so they can be previewed or selected when composing outbound messages."
        ),
        responses={
            200: OpenApiResponse(
                response=WhatsappTemplateListResponseSerializer,
                description="Templates available to the authenticated tenant",
                examples=[
                    OpenApiExample(
                        name="Template list",
                        value={
                            "templates": [
                                {
                                    "id": "205779699102012",
                                    "name": "welcome_message",
                                    "category": "MARKETING",
                                    "language": "en_US",
                                    "status": "APPROVED",
                                    "components": [
                                        {
                                            "type": "BODY",
                                            "text": "Hi {{1}}, thanks for contacting us!",
                                        }
                                    ],
                                }
                            ]
                        },
                    )
                ],
            )
        },
    )
    def list(self, request):
        tenant = self._get_tenant(request)
        client = self._get_client(tenant)
        if not client:
            return Response({"templates": []})

        templates = client.download_message_templates() or []
        data = [
            {
                "id": tpl.get("id"),
                "name": tpl.get("name"),
                "category": tpl.get("category"),
                "language": tpl.get("language"),
                "status": tpl.get("status", "UNKNOWN"),
                "components": tpl.get("components", []),
            }
            for tpl in templates
        ]
        return Response({"templates": data})

    @extend_schema(
        tags=["WhatsApp Templates"],
        summary="Retrieve WhatsApp template details",
        description=(
            "Fetches the full definition of a WhatsApp message template and the dynamic "
            "variables (requirements) that must be provided before sending."
        ),
        responses={
            200: OpenApiResponse(
                response=WhatsappTemplateDetailResponseSerializer,
                description="Template details and placeholder requirements",
                examples=[
                    OpenApiExample(
                        name="Template detail",
                        value={
                            "template": {
                                "id": "205779699102012",
                                "name": "welcome_message",
                                "language": "en_US",
                                "components": [
                                    {
                                        "type": "BODY",
                                        "text": "Hi {{1}}, thanks for contacting us!",
                                    }
                                ],
                            },
                            "requirements": [
                                {
                                    "type": "body",
                                    "parameters": [
                                        {"type": "text", "text": "{{1}}"}
                                    ],
                                }
                            ],
                        },
                    )
                ],
            ),
            400: OpenApiResponse(description="WhatsApp integration disabled or template not found"),
        },
    )
    def retrieve(self, request, pk=None):
        tenant = self._get_tenant(request)
        client = self._get_client(tenant)
        if not client:
            return Response(
                {"detail": "WhatsApp integration disabled"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        template = client.template_details(pk)
        requirements = template_requirements(template)
        return Response({"template": template, "requirements": requirements})

    @action(detail=True, methods=["post"], url_path="send-test")
    @extend_schema(
        tags=["WhatsApp Templates"],
        summary="Send a WhatsApp template test message",
        description=(
            "Sends a single WhatsApp message using the selected template to validate it "
            "before enabling automated campaigns. The request must include a destination "
            "phone number and any variables required by the template."
        ),
        request=WhatsappTemplateTestSerializer,
        responses={
            200: OpenApiResponse(
                response=WhatsappTemplateTestResponseSerializer,
                description="Message was accepted for delivery",
                examples=[OpenApiExample(name="Send success", value={"sent": True})],
            ),
            400: OpenApiResponse(
                description="Validation failed or WhatsApp integration disabled",
                examples=[OpenApiExample(name="Send failure", value={"sent": False})],
            ),
        },
    )
    def send_test(self, request, pk=None):
        tenant = self._get_tenant(request)
        client = self._get_client(tenant)
        if not client:
            return Response(
                {"detail": "WhatsApp integration disabled"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        serializer = WhatsappTemplateTestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        template = client.template_details(pk)
        requirements = template_requirements(template)
        values = serializer.validated_data.get("variables") or {}
        values["whatsapp_number"] = serializer.validated_data["phone"]
        components = replace_template_placeholders(requirements, values)
        namespace = client.retrieve_template_namespace()
        msg = compose_template_based_message(
            template,
            phone=serializer.validated_data["phone"],
            namespace=namespace,
            components=components,
        )
        send_result = client.send_message(msg, "template")
        success = isinstance(send_result, dict) and send_result.get("success", False)
        response_data = {"sent": success}
        if not success and isinstance(send_result, dict):
            response_data["error"] = send_result.get("error")
        status_code = status.HTTP_200_OK if success else status.HTTP_400_BAD_REQUEST
        return Response(response_data, status=status_code)

    def _get_client(self, tenant):
        if tenant is None:
            return None
        try:
            config = TenantConfiguration.objects.get(tenant=tenant)
        except TenantConfiguration.DoesNotExist:
            return None

        if not config.whatsapp_integration_enabled:
            return None
        return WhatsappBusinessClient(config)


class ToolCategory:
    CUSTOM = "custom"
    SEARCH = "search"
    COMMUNICATION = "communication"
    CRM = "crm"
    KNOWLEDGE = "knowledge"
    LOCATION = "location"
    ECOMMERCE = "ecommerce"
    UTILITY = "utility"
    BUILTIN = "builtin"


TOOL_CATEGORIES = {
    "send_comfort_message": ToolCategory.COMMUNICATION,
    "search_product": ToolCategory.ECOMMERCE,
    "search_product_by_tag": ToolCategory.ECOMMERCE,
    "get_full_product_catalog": ToolCategory.ECOMMERCE,
    "create_ticket": ToolCategory.CRM,
    "search_nearby_pos": ToolCategory.LOCATION,
    "get_tips": ToolCategory.KNOWLEDGE,
    "search_knowledge": ToolCategory.KNOWLEDGE,
    "search_knowledge_by_type": ToolCategory.KNOWLEDGE,
    "search_knowledge_item": ToolCategory.KNOWLEDGE,
    "end_conversation": ToolCategory.COMMUNICATION,
    "update_contact": ToolCategory.CRM,
    "schedule_callback": ToolCategory.CRM,
    "get_order_details": ToolCategory.ECOMMERCE,
    "get_orders": ToolCategory.ECOMMERCE,
    "calculate_delivery_date": ToolCategory.ECOMMERCE,
    "request_product_quote": ToolCategory.ECOMMERCE,
    "get_calendar_availability": ToolCategory.UTILITY,
    "create_appointment": ToolCategory.CRM,
    "register_activity": ToolCategory.CRM,
    "query_activities": ToolCategory.CRM,
}

BUILTIN_TOOLS = [
    {
        "name": "web_search",
        "display_name": "Web Search",
        "description": "Search the web for real-time information using a search engine.",
        "category": ToolCategory.BUILTIN,
        "type": "builtin",
        "config_key": "enable_websearch",
    },
    {
        "name": "file_search",
        "display_name": "File Search",
        "description": "Search through uploaded files and documents for relevant information.",
        "category": ToolCategory.BUILTIN,
        "type": "builtin",
        "requires_vector_store": True,
    },
    {
        "name": "code_interpreter",
        "display_name": "Code Interpreter",
        "description": "Execute Python code to perform calculations, data analysis, and generate visualizations.",
        "category": ToolCategory.BUILTIN,
        "type": "builtin",
    },
    {
        "name": "image_generation",
        "display_name": "Image Generation",
        "description": "Generate images based on text descriptions using DALL-E.",
        "category": ToolCategory.BUILTIN,
        "type": "builtin",
    },
]


def get_custom_tools():
    """
    Get all custom Moio tools from the tools repository.
    Returns a list of tool metadata including name, description, and category.
    """
    import inspect
    from agents.tool import FunctionTool
    import moio_platform.lib.moio_agent_tools_repo as tools_module

    tools_list = []

    for name, obj in inspect.getmembers(tools_module):
        if isinstance(obj, FunctionTool):
            tool_info = {
                "name": obj.name,
                "display_name": obj.name.replace("_", " ").title(),
                "description": obj.description or "",
                "category": TOOL_CATEGORIES.get(obj.name, ToolCategory.CUSTOM),
                "type": "custom",
            }
            tools_list.append(tool_info)

    return tools_list


class AvailableAgentToolsView(APIView):
    """
    API endpoint to list all available tools for agent configuration.

    GET /api/v1/resources/agent_tools/

    Returns:
        {
            "tools": [
                {
                    "name": "search_product",
                    "display_name": "Search Product",
                    "description": "Look up products matching search term",
                    "category": "ecommerce",
                    "type": "custom"
                },
                ...
            ],
            "categories": [
                {"id": "custom", "name": "Custom Tools"},
                {"id": "builtin", "name": "Built-in Tools"},
                ...
            ],
            "total": 20
        }
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        custom_tools = get_custom_tools()
        all_tools = custom_tools + BUILTIN_TOOLS

        all_tools.sort(key=lambda x: (x["category"], x["name"]))

        categories = [
            {"id": ToolCategory.BUILTIN, "name": "Built-in Tools", "description": "OpenAI Agents SDK built-in capabilities"},
            {"id": ToolCategory.CRM, "name": "CRM", "description": "Customer relationship management tools"},
            {"id": ToolCategory.COMMUNICATION, "name": "Communication", "description": "Messaging and notification tools"},
            {"id": ToolCategory.ECOMMERCE, "name": "E-Commerce", "description": "Product and order management tools"},
            {"id": ToolCategory.KNOWLEDGE, "name": "Knowledge", "description": "Knowledge base and FAQ tools"},
            {"id": ToolCategory.LOCATION, "name": "Location", "description": "Location and mapping tools"},
            {"id": ToolCategory.SEARCH, "name": "Search", "description": "Search and retrieval tools"},
            {"id": ToolCategory.UTILITY, "name": "Utility", "description": "General utility tools"},
            {"id": ToolCategory.CUSTOM, "name": "Custom", "description": "Other custom tools"},
        ]

        return Response({
            "tools": all_tools,
            "categories": categories,
            "total": len(all_tools),
        })

