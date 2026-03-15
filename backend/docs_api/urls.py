"""
URL configuration for Documentation API.

Endpoints:
- GET /api/docs/schema/           - Full OpenAPI schema
- GET /api/docs/navigation/       - Sidebar navigation structure
- GET /api/docs/guides/           - All guides by category
- GET /api/docs/guides/{slug}/    - Single guide detail
- GET /api/docs/endpoints/        - All API endpoints (paginated; filter by tag, search/name)
- GET /api/docs/endpoints/{id}/   - Single endpoint with full spec, response format, examples
- GET /api/docs/examples/{id}/    - Code examples for endpoint
- GET /api/docs/search/?q=        - Search guides and endpoints
- GET /api/docs/ingestion/status/ - Ingestion status
- POST /api/docs/validate/        - Validate document content
- GET /api/docs/template/         - Get document template
"""
from django.urls import path
from . import views

app_name = "docs_api"

urlpatterns = [
    # Schema
    path("schema/", views.DocsSchemaView.as_view(), name="schema"),
    
    # Navigation
    path("navigation/", views.DocsNavigationView.as_view(), name="navigation"),
    
    # Guides
    path("guides/", views.DocsGuidesView.as_view(), name="guides"),
    path("guides/<slug:slug>/", views.DocsGuideDetailView.as_view(), name="guide-detail"),
    
    # Endpoints
    path("endpoints/", views.DocsEndpointsView.as_view(), name="endpoints"),
    path("endpoints/<str:operation_id>/", views.DocsEndpointDetailView.as_view(), name="endpoint-detail"),
    
    # Code examples
    path("examples/<str:operation_id>/", views.DocsCodeExamplesView.as_view(), name="examples"),
    
    # Search
    path("search/", views.DocsSearchView.as_view(), name="search"),
    
    # Ingestion & Validation
    path("ingestion/status/", views.DocsIngestionView.as_view(), name="ingestion-status"),
    path("validate/", views.DocsValidateView.as_view(), name="validate"),
    path("template/", views.DocsTemplateView.as_view(), name="template"),
]
