"""
Reusable API Schema Components for drf-spectacular.

This module provides standardized schema components for consistent API documentation
across the entire Moio Platform.

Usage:
    from moio_platform.api_schemas import (
        STANDARD_ERRORS,
        Tags,
        paginated_response,
        success_response,
    )

    @extend_schema(
        tags=[Tags.CRM_CONTACTS],
        responses={200: ContactSerializer, **STANDARD_ERRORS},
    )
    def list(self, request):
        ...
"""

from rest_framework import serializers
from drf_spectacular.utils import (
    OpenApiExample,
    OpenApiResponse,
    OpenApiParameter,
    extend_schema,
    inline_serializer,
)
from drf_spectacular.types import OpenApiTypes


# ─────────────────────────────────────────────────────────────────────────────
# Tag Constants
# ─────────────────────────────────────────────────────────────────────────────

class Tags:
    """API tag constants for consistent grouping."""

    # Auth
    AUTH = "Auth"

    # CRM
    CRM_CONTACTS = "CRM - Contacts"
    CRM_TICKETS = "CRM - Tickets"
    CRM_DEALS = "CRM - Deals"
    CRM_PRODUCTS = "CRM - Products"
    CRM_KNOWLEDGE = "CRM - Knowledge"
    CRM_TAGS = "CRM - Tags"
    CRM_ACTIVITIES = "CRM - Activities"

    # Campaigns
    CAMPAIGNS = "Campaigns"
    AUDIENCES = "Audiences"

    # Flows
    FLOWS = "Flows"
    FLOW_EXECUTION = "Flow Execution"
    FLOW_SCHEDULES = "Flow Schedules"
    SCRIPTS = "Scripts"

    # Chatbot
    CHATBOT = "Chatbot"

    # DataLab
    DATALAB_FILES = "DataLab - Files"
    DATALAB_IMPORTS = "DataLab - Imports"
    DATALAB_RESULTSETS = "DataLab - ResultSets"
    DATALAB_DATASETS = "DataLab - Datasets"
    DATALAB_EXECUTE = "DataLab - Execute"

    # CMS/Commerce
    FLUIDCMS = "FluidCMS"
    FLUIDCOMMERCE = "FluidCommerce"

    # Other
    INTEGRATIONS = "Integrations"
    CALENDAR = "Calendar"
    RESOURCES = "Resources"
    SETTINGS = "Settings"
    HEALTH = "Health"




# ─────────────────────────────────────────────────────────────────────────────
# Standard Error Responses
# ─────────────────────────────────────────────────────────────────────────────

STANDARD_ERRORS = {
    400: OpenApiResponse(description="Bad Request - Invalid input data"),
    401: OpenApiResponse(description="Unauthorized - Invalid or missing token"),
    403: OpenApiResponse(description="Forbidden - Insufficient permissions"),
    404: OpenApiResponse(description="Not Found - Resource does not exist"),
    500: OpenApiResponse(description="Internal Server Error"),
}

# Subset for endpoints that don't require auth
STANDARD_ERRORS_NO_AUTH = {
    400: OpenApiResponse(description="Bad Request - Invalid input data"),
    404: OpenApiResponse(description="Not Found - Resource does not exist"),
    500: OpenApiResponse(description="Internal Server Error"),
}


# ─────────────────────────────────────────────────────────────────────────────
# Common Response Helpers
# ─────────────────────────────────────────────────────────────────────────────

def paginated_response(serializer_class, example_item: dict = None):
    """
    Create a paginated response schema.

    Usage:
        @extend_schema(responses={200: paginated_response(ContactSerializer)})
    """
    class PaginatedSerializer(serializers.Serializer):
        count = serializers.IntegerField(help_text="Total number of items")
        next = serializers.URLField(allow_null=True, help_text="URL to next page")
        previous = serializers.URLField(allow_null=True, help_text="URL to previous page")
        results = serializer_class(many=True)

    return PaginatedSerializer


def success_response(message: str = "Operation completed successfully"):
    """Create a simple success response schema."""
    return inline_serializer(
        name="SuccessResponse",
        fields={
            "success": serializers.BooleanField(default=True),
            "message": serializers.CharField(default=message),
        }
    )


def id_response(resource_name: str = "resource"):
    """Create a response schema returning just an ID."""
    return inline_serializer(
        name=f"{resource_name.title()}IdResponse",
        fields={
            "id": serializers.UUIDField(help_text=f"ID of the created {resource_name}"),
        }
    )


# ─────────────────────────────────────────────────────────────────────────────
# Common Parameters
# ─────────────────────────────────────────────────────────────────────────────

PAGINATION_PARAMS = [
    OpenApiParameter(
        name="page",
        type=int,
        location=OpenApiParameter.QUERY,
        description="Page number (1-indexed)",
        default=1,
    ),
    OpenApiParameter(
        name="page_size",
        type=int,
        location=OpenApiParameter.QUERY,
        description="Number of items per page (max 100)",
        default=20,
    ),
]

SEARCH_PARAM = OpenApiParameter(
    name="search",
    type=str,
    location=OpenApiParameter.QUERY,
    description="Search query string",
)

ORDERING_PARAM = OpenApiParameter(
    name="ordering",
    type=str,
    location=OpenApiParameter.QUERY,
    description="Field to sort by (prefix with - for descending)",
)

DATE_RANGE_PARAMS = [
    OpenApiParameter(
        name="created_after",
        type=OpenApiTypes.DATETIME,
        location=OpenApiParameter.QUERY,
        description="Filter by creation date (ISO 8601)",
    ),
    OpenApiParameter(
        name="created_before",
        type=OpenApiTypes.DATETIME,
        location=OpenApiParameter.QUERY,
        description="Filter by creation date (ISO 8601)",
    ),
]


# ─────────────────────────────────────────────────────────────────────────────
# Common Examples
# ─────────────────────────────────────────────────────────────────────────────

UUID_EXAMPLE = "550e8400-e29b-41d4-a716-446655440000"

PAGINATION_EXAMPLE = {
    "count": 150,
    "next": "https://api.moio.io/api/v1/contacts/?page=2",
    "previous": None,
    "results": [],
}


# ─────────────────────────────────────────────────────────────────────────────
# Decorator Helpers
# ─────────────────────────────────────────────────────────────────────────────

def schema_for_list(
    serializer_class,
    tag: str,
    summary: str = None,
    description: str = None,
    extra_params: list = None,
    extra_responses: dict = None,
):
    """
    Decorator factory for list endpoints.

    Usage:
        @schema_for_list(ContactSerializer, Tags.CRM_CONTACTS)
        def list(self, request):
            ...
    """
    params = PAGINATION_PARAMS + (extra_params or [])
    responses = {200: serializer_class(many=True), **STANDARD_ERRORS}
    if extra_responses:
        responses.update(extra_responses)

    return extend_schema(
        summary=summary or f"List {tag.split(' - ')[-1].lower()}",
        description=description,
        tags=[tag],
        parameters=params,
        responses=responses,
    )


def schema_for_retrieve(
    serializer_class,
    tag: str,
    summary: str = None,
    description: str = None,
):
    """Decorator factory for retrieve endpoints."""
    return extend_schema(
        summary=summary or f"Get {tag.split(' - ')[-1].lower()} details",
        description=description,
        tags=[tag],
        responses={200: serializer_class, **STANDARD_ERRORS},
    )


def schema_for_create(
    serializer_class,
    tag: str,
    summary: str = None,
    description: str = None,
    request_serializer=None,
):
    """Decorator factory for create endpoints."""
    return extend_schema(
        summary=summary or f"Create {tag.split(' - ')[-1].lower()}",
        description=description,
        tags=[tag],
        request=request_serializer or serializer_class,
        responses={201: serializer_class, **STANDARD_ERRORS},
    )


def schema_for_update(
    serializer_class,
    tag: str,
    summary: str = None,
    description: str = None,
):
    """Decorator factory for update endpoints."""
    return extend_schema(
        summary=summary or f"Update {tag.split(' - ')[-1].lower()}",
        description=description,
        tags=[tag],
        request=serializer_class,
        responses={200: serializer_class, **STANDARD_ERRORS},
    )


def schema_for_destroy(
    tag: str,
    summary: str = None,
    description: str = None,
):
    """Decorator factory for delete endpoints."""
    return extend_schema(
        summary=summary or f"Delete {tag.split(' - ')[-1].lower()}",
        description=description,
        tags=[tag],
        responses={
            204: OpenApiResponse(description="Successfully deleted"),
            **STANDARD_ERRORS,
        },
    )


def schema_for_action(
    tag: str,
    summary: str,
    description: str = None,
    request_serializer=None,
    response_serializer=None,
    responses: dict = None,
    methods: list = None,
):
    """Decorator factory for custom action endpoints."""
    final_responses = responses or {}
    if response_serializer:
        final_responses[200] = response_serializer
    final_responses.update(STANDARD_ERRORS)

    return extend_schema(
        summary=summary,
        description=description,
        tags=[tag],
        request=request_serializer,
        responses=final_responses,
        methods=methods,
    )
