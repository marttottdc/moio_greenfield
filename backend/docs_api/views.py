"""
Documentation API Views.

Provides endpoints for:
- OpenAPI schema (enhanced with examples/notes)
- Guides and tutorials
- Code examples
- Navigation structure
"""
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from django.shortcuts import get_object_or_404
from drf_spectacular.generators import SchemaGenerator
from drf_spectacular.utils import extend_schema, OpenApiParameter
from drf_spectacular.types import OpenApiTypes

from .models import GuideCategory, Guide, CodeExample, ApiEndpointNote
from .serializers import (
    GuideCategorySerializer,
    GuideDetailSerializer,
    GuideListSerializer,
    CodeExampleSerializer,
    ApiEndpointNoteSerializer,
)


class DocsSchemaView(APIView):
    """
    GET /api/docs/schema/
    
    Returns the OpenAPI schema with enhanced metadata.
    """
    permission_classes = [AllowAny]
    
    @extend_schema(exclude=True)
    def get(self, request):
        generator = SchemaGenerator()
        schema = generator.get_schema(request=request, public=True)
        
        # Convert to dict for JSON response
        if hasattr(schema, 'to_dict'):
            schema_dict = schema
        else:
            # Already a dict
            schema_dict = schema
        
        return Response(schema_dict)


class DocsNavigationView(APIView):
    """
    GET /api/docs/navigation/
    
    Returns the full navigation structure for the docs sidebar.
    Combines guides and API tags.
    """
    permission_classes = [AllowAny]
    
    @extend_schema(exclude=True)
    def get(self, request):
        navigation = []
        
        # Add guide categories
        categories = GuideCategory.objects.prefetch_related("guides").filter(
            guides__is_published=True
        ).distinct()
        
        for category in categories:
            nav_item = {
                "type": "guide-category",
                "slug": category.slug,
                "title": category.name,
                "icon": category.icon,
                "children": [
                    {
                        "type": "guide",
                        "slug": guide.slug,
                        "title": guide.title,
                    }
                    for guide in category.guides.filter(is_published=True)
                ]
            }
            navigation.append(nav_item)
        
        # Add API reference section from OpenAPI tags
        generator = SchemaGenerator()
        schema = generator.get_schema(request=request, public=True)
        
        api_tags = []
        if schema and "tags" in schema:
            for tag in schema["tags"]:
                api_tags.append({
                    "type": "api-tag",
                    "slug": tag["name"].lower().replace(" ", "-").replace("---", "-"),
                    "title": tag["name"],
                    "description": tag.get("description", ""),
                })
        
        if api_tags:
            navigation.append({
                "type": "section",
                "slug": "api-reference",
                "title": "API Reference",
                "icon": "code",
                "children": api_tags,
            })
        
        return Response({"navigation": navigation})


class DocsGuidesView(APIView):
    """
    GET /api/docs/guides/
    
    Returns all published guides grouped by category.
    """
    permission_classes = [AllowAny]
    
    @extend_schema(exclude=True)
    def get(self, request):
        categories = GuideCategory.objects.prefetch_related(
            "guides"
        ).filter(guides__is_published=True).distinct()
        
        serializer = GuideCategorySerializer(categories, many=True)
        return Response({"categories": serializer.data})


class DocsGuideDetailView(APIView):
    """
    GET /api/docs/guides/{slug}/
    
    Returns a single guide by slug.
    """
    permission_classes = [AllowAny]
    
    @extend_schema(exclude=True)
    def get(self, request, slug):
        guide = get_object_or_404(Guide, slug=slug, is_published=True)
        serializer = GuideDetailSerializer(guide)
        
        # Get adjacent guides for prev/next navigation
        same_category_guides = list(
            Guide.objects.filter(
                category=guide.category,
                is_published=True
            ).values_list("slug", "title")
        )
        
        current_index = None
        for i, (g_slug, _) in enumerate(same_category_guides):
            if g_slug == slug:
                current_index = i
                break
        
        prev_guide = None
        next_guide = None
        
        if current_index is not None:
            if current_index > 0:
                prev_guide = {
                    "slug": same_category_guides[current_index - 1][0],
                    "title": same_category_guides[current_index - 1][1],
                }
            if current_index < len(same_category_guides) - 1:
                next_guide = {
                    "slug": same_category_guides[current_index + 1][0],
                    "title": same_category_guides[current_index + 1][1],
                }
        
        return Response({
            "guide": serializer.data,
            "prev": prev_guide,
            "next": next_guide,
        })


def _build_endpoint_list_from_schema(schema, tag_filter=None, name_filter=None):
    """Build list of endpoint items from OpenAPI schema with optional tag and name filter."""
    endpoints = []
    if not schema or "paths" not in schema:
        return endpoints

    name_lower = (name_filter or "").strip().lower()

    for path, methods in schema["paths"].items():
        for method, details in methods.items():
            if method not in ["get", "post", "put", "patch", "delete"]:
                continue
            tags = details.get("tags", [])
            if tag_filter and tag_filter not in tags:
                continue

            if name_lower:
                searchable = " ".join([
                    path,
                    details.get("operationId", ""),
                    details.get("summary", ""),
                    details.get("description", ""),
                    " ".join(tags),
                ]).lower()
                if name_lower not in searchable:
                    continue

            # Derive response format and request body summary from OpenAPI spec
            response_format = _response_format_summary(details.get("responses") or {})
            request_body = _request_body_summary(details.get("requestBody"))

            endpoints.append({
                "operation_id": details.get("operationId", ""),
                "path": path,
                "method": method.upper(),
                "summary": details.get("summary", ""),
                "description": details.get("description", ""),
                "tags": tags,
                "deprecated": details.get("deprecated", False),
                "response_format": response_format,
                "request_body": request_body,
                "form_component": details.get("x-form-component"),
            })
    return endpoints


def _request_body_summary(request_body):
    """Build a short request body summary from OpenAPI requestBody."""
    if not request_body or not isinstance(request_body, dict):
        return None
    out = []
    content = request_body.get("content", {}) or {}
    for media_type, media_spec in content.items():
        schema_ref = None
        if isinstance(media_spec, dict) and "schema" in media_spec:
            s = media_spec["schema"]
            if isinstance(s, dict) and "$ref" in s:
                schema_ref = s["$ref"].split("/")[-1]
            elif isinstance(s, dict) and "type" in s:
                schema_ref = s.get("type", "object")
        out.append({"content_type": media_type, "schema": schema_ref or "object"})
    return out if out else None


def _response_format_summary(responses):
    """Build a short response format summary from OpenAPI responses dict."""
    out = []
    for status_code, content in sorted(responses.items()):
        desc = content.get("description", "")
        content_media = content.get("content", {}) or {}
        for media_type, media_spec in content_media.items():
            schema_ref = None
            if isinstance(media_spec, dict) and "schema" in media_spec:
                s = media_spec["schema"]
                if isinstance(s, dict) and "$ref" in s:
                    schema_ref = s["$ref"].split("/")[-1]
                elif isinstance(s, dict) and "type" in s:
                    schema_ref = s.get("type", "object")
            if schema_ref:
                out.append({"status": status_code, "content_type": media_type, "schema": schema_ref})
            else:
                out.append({"status": status_code, "content_type": media_type, "description": desc or ""})
    return out if out else [{"description": "No response schema documented"}]


class DocsEndpointsView(APIView):
    """
    GET /api/docs/endpoints/

    List all API endpoints with spec, method, and response format.
    Paginated and filterable by tag and name (search).
    """
    permission_classes = [AllowAny]

    @extend_schema(
        exclude=True,
        parameters=[
            OpenApiParameter("tag", OpenApiTypes.STR, description="Filter by OpenAPI tag"),
            OpenApiParameter("search", OpenApiTypes.STR, description="Filter by name (path, operationId, summary, tags)"),
            OpenApiParameter("name", OpenApiTypes.STR, description="Alias for search"),
            OpenApiParameter("page", OpenApiTypes.INT, description="Page number (default 1)"),
            OpenApiParameter("page_size", OpenApiTypes.INT, description="Items per page (default 20, max 100)"),
        ],
    )
    def get(self, request):
        tag_filter = request.query_params.get("tag", "").strip() or None
        name_filter = request.query_params.get("search") or request.query_params.get("name") or request.query_params.get("q")
        try:
            page = max(1, int(request.query_params.get("page", 1)))
        except (TypeError, ValueError):
            page = 1
        try:
            page_size = min(100, max(1, int(request.query_params.get("page_size", request.query_params.get("limit", 20)))))
        except (TypeError, ValueError):
            page_size = 20

        generator = SchemaGenerator()
        schema = generator.get_schema(request=request, public=True)
        endpoints = _build_endpoint_list_from_schema(schema, tag_filter=tag_filter, name_filter=name_filter)

        total = len(endpoints)
        start = (page - 1) * page_size
        end = start + page_size
        page_items = endpoints[start:end]

        return Response({
            "endpoints": page_items,
            "count": len(page_items),
            "total_count": total,
            "page": page,
            "page_size": page_size,
            "total_pages": (total + page_size - 1) // page_size if page_size else 0,
        })


class DocsEndpointDetailView(APIView):
    """
    GET /api/docs/endpoints/{operation_id}/
    
    Returns full details for a specific endpoint including:
    - OpenAPI spec
    - Code examples
    - Notes/warnings
    """
    permission_classes = [AllowAny]
    
    @extend_schema(exclude=True)
    def get(self, request, operation_id):
        generator = SchemaGenerator()
        schema = generator.get_schema(request=request, public=True)
        
        endpoint_spec = None
        
        if schema and "paths" in schema:
            for path, methods in schema["paths"].items():
                for method, details in methods.items():
                    if details.get("operationId") == operation_id:
                        endpoint_spec = {
                            "path": path,
                            "method": method.upper(),
                            **details,
                        }
                        break
                if endpoint_spec:
                    break
        
        if not endpoint_spec:
            return Response(
                {"error": "Endpoint not found"},
                status=status.HTTP_404_NOT_FOUND
            )
        
        # Get code examples
        examples = CodeExample.objects.filter(operation_id=operation_id)
        examples_serializer = CodeExampleSerializer(examples, many=True)
        
        # Get notes
        notes = ApiEndpointNote.objects.filter(operation_id=operation_id)
        notes_serializer = ApiEndpointNoteSerializer(notes, many=True)
        
        # Get referenced schemas
        referenced_schemas = {}
        if "components" in schema and "schemas" in schema["components"]:
            # Extract schemas referenced by this endpoint
            spec_str = str(endpoint_spec)
            for schema_name, schema_def in schema["components"]["schemas"].items():
                if f"#/components/schemas/{schema_name}" in spec_str:
                    referenced_schemas[schema_name] = schema_def
        
        response_format = _response_format_summary(endpoint_spec.get("responses") or {})
        request_body = _request_body_summary(endpoint_spec.get("requestBody"))

        return Response({
            "spec": endpoint_spec,
            "response_format": response_format,
            "request_body": request_body,
            "form_component": endpoint_spec.get("x-form-component"),
            "examples": examples_serializer.data,
            "notes": notes_serializer.data,
            "schemas": referenced_schemas,
        })


class DocsCodeExamplesView(APIView):
    """
    GET /api/docs/examples/{operation_id}/
    
    Returns code examples for a specific endpoint.
    """
    permission_classes = [AllowAny]
    
    @extend_schema(exclude=True)
    def get(self, request, operation_id):
        examples = CodeExample.objects.filter(operation_id=operation_id)
        
        if not examples.exists():
            # Generate basic examples if none exist
            examples_data = self._generate_default_examples(request, operation_id)
        else:
            examples_data = CodeExampleSerializer(examples, many=True).data
        
        return Response({"examples": examples_data})
    
    def _generate_default_examples(self, request, operation_id):
        """Generate basic code examples from the OpenAPI spec."""
        generator = SchemaGenerator()
        schema = generator.get_schema(request=request, public=True)
        
        endpoint_spec = None
        path = None
        method = None
        
        if schema and "paths" in schema:
            for p, methods in schema["paths"].items():
                for m, details in methods.items():
                    if details.get("operationId") == operation_id:
                        endpoint_spec = details
                        path = p
                        method = m.upper()
                        break
                if endpoint_spec:
                    break
        
        if not endpoint_spec:
            return []
        
        base_url = request.build_absolute_uri("/").rstrip("/")
        full_url = f"{base_url}{path}"
        
        examples = []
        
        # cURL example
        curl_example = f'curl -X {method} "{full_url}" \\\n'
        curl_example += '  -H "Authorization: Bearer YOUR_TOKEN" \\\n'
        curl_example += '  -H "Content-Type: application/json"'
        
        if method in ["POST", "PUT", "PATCH"]:
            curl_example += ' \\\n  -d \'{"key": "value"}\''
        
        examples.append({
            "language": "curl",
            "language_display": "cURL",
            "title": f"{method} {path}",
            "code": curl_example,
            "description": "Basic request example",
        })
        
        # Python example
        python_example = f'''import requests

url = "{full_url}"
headers = {{
    "Authorization": "Bearer YOUR_TOKEN",
    "Content-Type": "application/json"
}}
'''
        if method == "GET":
            python_example += f'''
response = requests.get(url, headers=headers)
print(response.json())'''
        elif method == "POST":
            python_example += f'''
data = {{"key": "value"}}

response = requests.post(url, json=data, headers=headers)
print(response.json())'''
        elif method == "DELETE":
            python_example += f'''
response = requests.delete(url, headers=headers)
print(response.status_code)'''
        else:
            python_example += f'''
data = {{"key": "value"}}

response = requests.{method.lower()}(url, json=data, headers=headers)
print(response.json())'''
        
        examples.append({
            "language": "python",
            "language_display": "Python",
            "title": f"{method} {path}",
            "code": python_example,
            "description": "Python requests example",
        })
        
        # JavaScript example
        js_example = f'''const response = await fetch("{full_url}", {{
  method: "{method}",
  headers: {{
    "Authorization": "Bearer YOUR_TOKEN",
    "Content-Type": "application/json"
  }},'''
        
        if method in ["POST", "PUT", "PATCH"]:
            js_example += '''
  body: JSON.stringify({ key: "value" })'''
        
        js_example += '''
});

const data = await response.json();
console.log(data);'''
        
        examples.append({
            "language": "javascript",
            "language_display": "JavaScript",
            "title": f"{method} {path}",
            "code": js_example,
            "description": "Fetch API example",
        })
        
        return examples


class DocsSearchView(APIView):
    """
    GET /api/docs/search/?q=contacts
    
    Search across guides and API endpoints.
    """
    permission_classes = [AllowAny]
    
    @extend_schema(exclude=True)
    def get(self, request):
        query = request.query_params.get("q", "").strip()
        
        if len(query) < 2:
            return Response({
                "error": "Query must be at least 2 characters"
            }, status=status.HTTP_400_BAD_REQUEST)
        
        results = {
            "guides": [],
            "endpoints": [],
        }
        
        # Search guides
        from django.db.models import Q
        guides = Guide.objects.filter(
            is_published=True
        ).filter(
            Q(title__icontains=query) |
            Q(summary__icontains=query) |
            Q(content__icontains=query)
        )[:10]
        
        results["guides"] = GuideListSerializer(guides, many=True).data
        
        # Search endpoints
        generator = SchemaGenerator()
        schema = generator.get_schema(request=request, public=True)
        
        query_lower = query.lower()
        
        if schema and "paths" in schema:
            for path, methods in schema["paths"].items():
                for method, details in methods.items():
                    if method in ["get", "post", "put", "patch", "delete"]:
                        searchable = f"{path} {details.get('summary', '')} {details.get('description', '')} {' '.join(details.get('tags', []))}".lower()
                        
                        if query_lower in searchable:
                            results["endpoints"].append({
                                "operation_id": details.get("operationId", ""),
                                "path": path,
                                "method": method.upper(),
                                "summary": details.get("summary", ""),
                                "tags": details.get("tags", []),
                            })
                            
                            if len(results["endpoints"]) >= 10:
                                break
                
                if len(results["endpoints"]) >= 10:
                    break
        
        return Response(results)


class DocsIngestionView(APIView):
    """
    Manage documentation ingestion.
    
    GET  /api/docs/ingestion/status/    - Get ingestion status
    POST /api/docs/ingestion/validate/  - Validate a document
    POST /api/docs/ingestion/import/    - Import documents from folder
    """
    permission_classes = [IsAuthenticated]
    
    @extend_schema(exclude=True)
    def get(self, request):
        """Get ingestion status."""
        from django.conf import settings
        from pathlib import Path
        from docs_api.ingestion import DocumentIngestor
        
        source_dir = Path(settings.BASE_DIR) / "docs" / "content"
        ingestor = DocumentIngestor(source_dir=str(source_dir))
        
        return Response(ingestor.get_status())


class DocsValidateView(APIView):
    """
    POST /api/docs/validate/
    
    Validate a document without importing.
    """
    permission_classes = [IsAuthenticated]
    
    @extend_schema(exclude=True)
    def post(self, request):
        """Validate document content."""
        from docs_api.ingestion import DocumentValidator
        
        content = request.data.get("content", "")
        
        if not content:
            return Response(
                {"error": "content field is required"},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        validator = DocumentValidator()
        result = validator.validate_content(content)
        
        return Response(result.to_dict())


class DocsTemplateView(APIView):
    """
    GET /api/docs/template/?type=guide
    
    Get a document template.
    """
    permission_classes = [AllowAny]
    
    @extend_schema(exclude=True)
    def get(self, request):
        """Get document template."""
        from docs_api.ingestion.ingestor import create_template
        from docs_api.ingestion import schema
        
        doc_type = request.query_params.get("type", "guide")
        
        if doc_type not in schema.DOCUMENT_TYPES:
            return Response(
                {"error": f"Invalid type. Valid: {list(schema.DOCUMENT_TYPES.keys())}"},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        template = create_template(doc_type)
        
        return Response({
            "type": doc_type,
            "template": template,
            "required_sections": schema.DOCUMENT_TYPES[doc_type]["required_sections"],
            "optional_sections": schema.DOCUMENT_TYPES[doc_type]["optional_sections"],
        })
