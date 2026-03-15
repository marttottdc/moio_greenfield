from drf_spectacular.utils import extend_schema, OpenApiResponse
from rest_framework.response import Response

from crm.api.mixins import ProtectedAPIView
from crm.api.data_store import demo_store


@extend_schema(tags=["templates"])
class TemplateListView(ProtectedAPIView):
    @extend_schema(summary="List templates", description="List available templates from demo store.", responses={200: OpenApiResponse(description="templates")})
    def get(self, request):
        return Response({"templates": demo_store.list_templates()})

