"""
Global URL configuration.
Groups:
1. Webhooks (external callbacks)
2. Public API (v1)
3. API Schema & Docs
4. Internal/Event Stream
"""

from django.urls import include, path
from rest_framework.decorators import api_view
from rest_framework.response import Response
from chatbot.views import whatsapp_webhook_receiver, instagram_webhook_receiver, messenger_webhook_receiver
from crm.views import generic_webhook_receiver

from moio_platform.core import core_views
from moio_platform.core.health import health_check, probe_health
from portal.api.bootstrap import BootstrapView
from crm.api.auth.views import AuthViewSet
from drf_spectacular.views import (
    SpectacularAPIView,
)

# -----------------------
# Simple test endpoint
# -----------------------
@api_view(["GET"])
def test_api(request):
    return Response({"message": "DRF is working!"})


# -----------------------
# Custom HTTP handlers
# -----------------------
handler400 = core_views.handler400
handler403 = core_views.handler403
handler404 = core_views.handler404
handler500 = core_views.handler500


# -----------------------
# Global URL routing
# -----------------------
urlpatterns = [

    # 1️⃣ Webhooks (external services)
    path("webhooks/whatsapp/", whatsapp_webhook_receiver, name="whatsapp_webhook_receiver"),
    path("webhooks/instagram/", instagram_webhook_receiver, name="instagram_webhook_receiver"),
    path("webhooks/messenger/", messenger_webhook_receiver, name="messenger_webhook_receiver"),
    path("webhooks/<str:webhook_id>/", generic_webhook_receiver, name="generic_webhook_receiver"),

    # Health (infra probes / load balancers)
    path("health", probe_health, name="probe_health_root_noslash"),
    path("health/", probe_health, name="probe_health_root"),

    # 2️⃣ Public API v1 (REST)
    # Accept both trailing and non-trailing slash variants to avoid proxy redirect loops.
    path("api/v1/auth/login", AuthViewSet.as_view({"post": "login"})),
    path("api/v1/auth/refresh", AuthViewSet.as_view({"post": "refresh"})),
    path("api/v1/auth/me", AuthViewSet.as_view({"get": "me"})),
    path("api/v1/auth/logout", AuthViewSet.as_view({"post": "logout"})),
    path("api/v1/auth/", include("crm.api.auth.urls")),

    path("api/v1/health/", health_check, name="health_check"),
    path("api/v1/bootstrap/", BootstrapView.as_view(), name="bootstrap"),
    path("api/v1/tenants/", include("portal.api.tenants.urls")),
    path("api/v1/users/", include("portal.api.users.urls")),
    path("api/v1/settings/", include("crm.api.settings.urls")),
    path("api/v1/integrations/", include("portal.integrations.urls")),
    path("api/v1/crm/", include("crm.api.public_urls")),
    path("api/v1/activities/", include("crm.api.activities.urls")),
    path("api/v1/capture/", include("crm.api.capture.urls")),
    path("api/v1/timeline/", include("crm.api.timeline.urls")),
    path("api/v1/resources/", include("resources.api.urls")),
    path("api/v1/campaigns/", include("campaigns.api.urls")),

    path("api/v1/flows/", include(("flows.api_urls", "flows_api"), namespace="flows_api")),
    path("api/v1/robots/", include("robots.api_urls")),
    path("api/v1/scripts/", include("flows.api_script_urls")),
    path("api/v1/test/", test_api),
    path("api/v1/fluidcms/", include("fluidcms.urls")),
    path("api/v1/fluidcommerce/", include("fluidcommerce.urls")),
    path("api/v1/desktop-agent/", include("chatbot.api.urls")),
    path("api/v1/datalab/", include("datalab.api.urls")),

    # 3️⃣ API Documentation & Schema
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    
    # Documentation API (for custom React frontend)
    path("api/docs/", include("docs_api.urls", namespace="docs_api")),

    # MCP Server URLs (AI Assistants / Tools)
    path("", include("mcp_server.urls")),
]
