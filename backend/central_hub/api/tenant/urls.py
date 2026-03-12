"""
Tenant Admin API routes: /api/tenant/*
"""
from django.urls import path

from .views import (
    TenantBootstrapView,
    TenantPluginsView,
    TenantUsersDeleteView,
    TenantUsersSaveView,
    TenantWorkspacesDeleteView,
    TenantWorkspacesSaveView,
)

urlpatterns = [
    path("bootstrap/", TenantBootstrapView.as_view(), name="tenant_bootstrap"),
    path("bootstrap", TenantBootstrapView.as_view(), name="tenant_bootstrap_noslash"),
    path("users/", TenantUsersSaveView.as_view(), name="tenant_users_save"),
    path("users", TenantUsersSaveView.as_view(), name="tenant_users_save_noslash"),
    path("users/delete/", TenantUsersDeleteView.as_view(), name="tenant_users_delete"),
    path("users/delete", TenantUsersDeleteView.as_view(), name="tenant_users_delete_noslash"),
    path("workspaces/", TenantWorkspacesSaveView.as_view(), name="tenant_workspaces_save"),
    path("workspaces", TenantWorkspacesSaveView.as_view(), name="tenant_workspaces_save_noslash"),
    path("workspaces/delete/", TenantWorkspacesDeleteView.as_view(), name="tenant_workspaces_delete"),
    path("workspaces/delete", TenantWorkspacesDeleteView.as_view(), name="tenant_workspaces_delete_noslash"),
    path("plugins/", TenantPluginsView.as_view(), name="tenant_plugins"),
    path("plugins", TenantPluginsView.as_view(), name="tenant_plugins_noslash"),
]
