from drf_spectacular.utils import extend_schema
from rest_framework.response import Response

from crm.api.mixins import ProtectedAPIView
from crm.api.data_store import demo_store


@extend_schema(tags=["templates"])
class TemplateListView(ProtectedAPIView):
    def get(self, request):
        return Response({"templates": demo_store.list_templates()})

