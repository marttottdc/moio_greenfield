"""
API meta views: endpoint inventory for agent console (moio_api.run) and other consumers.
"""
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from drf_spectacular.generators import SchemaGenerator


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def meta_endpoints(request):
    """
    GET /api/v1/meta/endpoints/

    Returns a list of API endpoint contracts (method, path, summary, etc.)
    so agent tools (e.g. moio_api.run) can discover and call platform APIs.
    """
    generator = SchemaGenerator()
    schema = generator.get_schema(request=request, public=True)
    endpoints = []
    if schema and "paths" in schema:
        for path, methods in schema["paths"].items():
            for method, details in methods.items():
                if method.lower() in ("get", "post", "put", "patch", "delete"):
                    endpoints.append({
                        "method": method.upper(),
                        "path": path,
                        "operationId": details.get("operationId", ""),
                        "summary": details.get("summary", ""),
                        "description": details.get("description", ""),
                        "tags": details.get("tags", []),
                    })
    return Response({"endpoints": endpoints, "count": len(endpoints)})
