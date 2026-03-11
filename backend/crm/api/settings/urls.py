from django.urls import path, include
from rest_framework.routers import SimpleRouter

from .views import (
    AgentConfigurationViewSet,
    TenantConfigurationViewSet,
    IntegrationViewSet,
    PreferencesViewSet,
    LocalizationViewSet,
)
from chatbot.api.views.tenant_tools import TenantToolConfigurationViewSet

router = SimpleRouter()
router.register(r'agents', AgentConfigurationViewSet, basename='settings-agent')
router.register(r'integrations', IntegrationViewSet, basename='settings-integration')

# Tools router - register directly with explicit paths to avoid conflicts
tools_viewset = TenantToolConfigurationViewSet.as_view({
    'get': 'list',
    'post': 'create',
})

tool_detail_viewset = TenantToolConfigurationViewSet.as_view({
    'get': 'retrieve',
    'patch': 'partial_update',
    'put': 'update',
    'delete': 'destroy',
})

tenant_settings_view = TenantConfigurationViewSet.as_view(
    {
        'get': 'retrieve',
        'patch': 'partial_update',
    }
)

preferences_view = PreferencesViewSet.as_view(
    {
        'get': 'retrieve',
        'patch': 'partial_update',
    }
)

localization_view = LocalizationViewSet.as_view(
    {
        'get': 'retrieve',
        'patch': 'partial_update',
    }
)

urlpatterns = [
    # Tools endpoints - explicit paths to avoid routing conflicts
    path('agents/tools/', tools_viewset, name='settings-agent-tools-list'),
    path('agents/tools/<str:tool_name>/', tool_detail_viewset, name='settings-agent-tools-detail'),
] + router.urls + [
    path('preferences/', preferences_view, name='settings-preferences'),
    path('localization/', localization_view, name='settings-localization'),
    path('<slug:integration>/', tenant_settings_view, name='tenant-settings-detail'),
]
