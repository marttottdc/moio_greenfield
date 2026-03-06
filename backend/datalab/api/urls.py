"""
URL configuration for Data Lab API endpoints.
"""
from django.urls import path, include
from rest_framework.routers import DefaultRouter

from . import views, crm_views, panels, execute_views
from .views import (
    ImportProcessViewSet, ImportRunViewSet,
    DataSourceViewSet, DatasetViewSet, DatasetVersionViewSet
)

router = DefaultRouter()
router.register(r'files', views.FileAssetViewSet, basename='datalab-file')
router.register(r'filesets', views.FileSetViewSet, basename='datalab-fileset')
router.register(r'imports', views.ImportViewSet, basename='datalab-import')
router.register(r'resultsets', views.ResultSetViewSet, basename='datalab-resultset')
router.register(r'crm/views', crm_views.CRMViewViewSet, basename='datalab-crm-view')
router.register(r'crm/query', crm_views.CRMQueryViewSet, basename='datalab-crm-query')
router.register(r'panels', panels.PanelViewSet, basename='datalab-panel')
router.register(r'widgets', panels.WidgetViewSet, basename='datalab-widget')
router.register(r'import-processes', ImportProcessViewSet, basename='datalab-import-process')
router.register(r'import-runs', ImportRunViewSet, basename='datalab-import-run')
router.register(r'data-sources', DataSourceViewSet, basename='datalab-data-source')
router.register(r'datasets', DatasetViewSet, basename='datalab-dataset')
router.register(r'dataset-versions', DatasetVersionViewSet, basename='datalab-dataset-version')

urlpatterns = [
    path('', include(router.urls)),
    path('execute/', execute_views.ExecuteView.as_view(), name='datalab-execute'),
    # Analytics API (v4)
    path('', include('datalab.analytics.api.urls')),
]
