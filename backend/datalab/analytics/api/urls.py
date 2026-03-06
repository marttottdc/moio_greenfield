"""
URL configuration for Analytics API.

All endpoints are prefixed with /api/v1/datalab/
"""

from django.urls import path, include
from rest_framework.routers import DefaultRouter

from datalab.analytics.api.views import (
    AnalysisModelViewSet,
    AnalyzerViewSet,
    AnalyzerRunViewSet
)

router = DefaultRouter()
router.register('analysis-models', AnalysisModelViewSet, basename='analysis-model')
router.register('analyzer-runs', AnalyzerRunViewSet, basename='analyzer-run')

urlpatterns = [
    path('', include(router.urls)),
    path('analyze/', AnalyzerViewSet.as_view({'post': 'create'}), name='analyze'),
]
