"""
Integration API URL patterns.

Endpoints:
- GET  /integrations/                              - List available integrations
- GET  /integrations/categories/                   - List integration categories
- GET  /integrations/{slug}/schema/                - Get integration schema
- GET  /integrations/{slug}/                       - List configs for integration
- POST /integrations/{slug}/                       - Create new config
- GET  /integrations/{slug}/{instance_id}/         - Get specific config
- PATCH /integrations/{slug}/{instance_id}/        - Update config
- PUT  /integrations/{slug}/{instance_id}/         - Replace config
- DELETE /integrations/{slug}/{instance_id}/       - Delete config
- GET  /integrations/{slug}/{instance_id}/public/  - Get public/frontend-safe config
"""

from django.urls import path, include

from portal.integrations.views import (
    IntegrationListView,
    IntegrationSchemaView,
    IntegrationConfigListView,
    IntegrationConfigDetailView,
    IntegrationCategoriesView,
    IntegrationPublicConfigView,
    WhatsappEmbeddedSignupConfigView,
    WhatsappEmbeddedSignupCompleteView,
    WhatsappEmbeddedSignupCallbackView,
)


urlpatterns = [
    # v1 email + calendar routes (must precede slug catch-alls)
    path("", include("portal.integrations.v1.urls")),

    path("", IntegrationListView.as_view(), name="integration_list"),
    path("categories/", IntegrationCategoriesView.as_view(), name="integration_categories"),
    path("<str:slug>/schema/", IntegrationSchemaView.as_view(), name="integration_schema"),
    # WhatsApp embedded signup helpers
    path(
        "whatsapp/embedded-signup/config/",
        WhatsappEmbeddedSignupConfigView.as_view(),
        name="whatsapp_embedded_signup_config",
    ),
    path(
        "whatsapp/embedded-signup/complete/",
        WhatsappEmbeddedSignupCompleteView.as_view(),
        name="whatsapp_embedded_signup_complete",
    ),
    path(
        "whatsapp/embedded-signup/callback/",
        WhatsappEmbeddedSignupCallbackView.as_view(),
        name="whatsapp_embedded_signup_callback",
    ),
    path("<str:slug>/", IntegrationConfigListView.as_view(), name="integration_config_list"),
    path("<str:slug>/<str:instance_id>/", IntegrationConfigDetailView.as_view(), name="integration_config_detail"),
    path("<str:slug>/<str:instance_id>/public/", IntegrationPublicConfigView.as_view(), name="integration_public_config"),
]
