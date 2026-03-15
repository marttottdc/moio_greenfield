"""
URL routing for Platform Admin API: /api/platform/*
"""
from django.urls import path

from central_hub.api.platform_bootstrap import PlatformBootstrapView
from central_hub.api.platform.views import (
    PlatformConfigurationSaveView,
    PlatformIntegrationsDeleteView,
    PlatformIntegrationsSaveView,
    PlatformAdminKPIsView,
    PlatformAdminKPIsRefreshView,
    PlatformAdminKPIsRefreshStatusView,
    PlatformNotificationsSaveView,
    PlatformPluginsView,
    PlatformPlansDeleteView,
    PlatformPlansSaveView,
    PlatformRolesDeleteView,
    PlatformRolesSaveView,
    PlatformSkillsDeleteView,
    PlatformSkillsSaveView,
    PlatformTenantIntegrationsSaveView,
    PlatformTenantsCreateView,
    PlatformTenantsDeleteView,
    PlatformTenantsUpdateView,
    PlatformUsersDeleteView,
    PlatformUsersSaveView,
)

urlpatterns = [
    path("bootstrap/", PlatformBootstrapView.as_view(), name="platform_bootstrap"),
    path("bootstrap", PlatformBootstrapView.as_view(), name="platform_bootstrap_noslash"),
    path("kpis/", PlatformAdminKPIsView.as_view(), name="platform_kpis"),
    path("kpis/refresh/", PlatformAdminKPIsRefreshView.as_view(), name="platform_kpis_refresh"),
    path("kpis/refresh/status/", PlatformAdminKPIsRefreshStatusView.as_view(), name="platform_kpis_refresh_status"),
    path("plans/", PlatformPlansSaveView.as_view(), name="platform_plans_save"),
    path("plans/delete/", PlatformPlansDeleteView.as_view(), name="platform_plans_delete"),
    path("roles/", PlatformRolesSaveView.as_view(), name="platform_roles_save"),
    path("roles/delete/", PlatformRolesDeleteView.as_view(), name="platform_roles_delete"),
    path("tenants/", PlatformTenantsCreateView.as_view(), name="platform_tenants_create"),
    path("tenants/update/", PlatformTenantsUpdateView.as_view(), name="platform_tenants_update"),
    path("tenants/update", PlatformTenantsUpdateView.as_view(), name="platform_tenants_update_noslash"),
    path("tenants/delete/", PlatformTenantsDeleteView.as_view(), name="platform_tenants_delete"),
    path("users/", PlatformUsersSaveView.as_view(), name="platform_users_save"),
    path("users/delete/", PlatformUsersDeleteView.as_view(), name="platform_users_delete"),
    path("integrations/", PlatformIntegrationsSaveView.as_view(), name="platform_integrations_save"),
    path("integrations/delete/", PlatformIntegrationsDeleteView.as_view(), name="platform_integrations_delete"),
    path("tenant-integrations/", PlatformTenantIntegrationsSaveView.as_view(), name="platform_tenant_integrations_save"),
    path("configuration/", PlatformConfigurationSaveView.as_view(), name="platform_configuration_save"),
    path("notifications/", PlatformNotificationsSaveView.as_view(), name="platform_notifications_save"),
    path("skills/", PlatformSkillsSaveView.as_view(), name="platform_skills_save"),
    path("skills/delete/", PlatformSkillsDeleteView.as_view(), name="platform_skills_delete"),
    path("plugins/", PlatformPluginsView.as_view(), name="platform_plugins"),
    path("plugins", PlatformPluginsView.as_view(), name="platform_plugins_noslash"),
]
