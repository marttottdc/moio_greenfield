"""URL router for shared resource endpoints."""

from django.urls import include, path
from rest_framework.routers import DefaultRouter

from crm.api.settings.views import WebhookConfigViewSet
from resources.api.views import ContactSearchView, WhatsappTemplateViewSet, AvailableAgentToolsView

router = DefaultRouter()
router.register(
    r"whatsapp-templates",
    WhatsappTemplateViewSet,
    basename="resource-whatsapp-templates",
)
router.register(
    r"webhooks",
    WebhookConfigViewSet,
    basename="resource-webhooks",
)

urlpatterns = [
    path("", include(router.urls)),
    path("contacts/search/", ContactSearchView.as_view(), name="resource-contact-search"),
    path("agent_tools/", AvailableAgentToolsView.as_view(), name="resource-agent-tools"),
]
