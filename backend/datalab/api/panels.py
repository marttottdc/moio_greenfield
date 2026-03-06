"""
API views for Data Lab Panels and Widgets.
"""
from __future__ import annotations

import logging

from django.db import models
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from datalab.api.views import AuthenticatedDataLabView
from datalab.panels.models import Panel, Widget
from datalab.panels.services import PanelService
from datalab.panels.widget_runners import get_widget_runner, WidgetRunnerError

from . import serializers

logger = logging.getLogger(__name__)


class PanelViewSet(AuthenticatedDataLabView, viewsets.ModelViewSet):
    """ViewSet for Panels."""
    
    serializer_class = serializers.PanelSerializer
    
    def get_queryset(self):
        """Get panels for current tenant."""
        tenant = self.get_tenant(self.request)
        # Filter by visibility (public or user's own)
        user = self.request.user
        
        queryset = Panel.objects.filter(tenant=tenant)
        
        # If not admin, filter to public or own panels
        if not (user and user.is_staff):
            queryset = queryset.filter(
                models.Q(is_public=True) | models.Q(created_by=user)
            )
        
        return queryset.order_by('-created_at')
    
    def perform_create(self, serializer):
        """Create a new panel."""
        tenant = self.get_tenant(self.request)
        analysis_model = serializer.validated_data.get('analysis_model')
        if analysis_model is None:
            raise serializers.ValidationError({"analysis_model": "analysis_model is required"})
        serializer.save(tenant=tenant, created_by=self.request.user)
    
    @action(detail=True, methods=['post'])
    def execute(self, request, pk=None):
        """
        Execute the panel's bound Analysis Model via AnalyzerService.
        
        This runs the Analyzer with the panel's default_parameters_json merged
        with any overrides provided in the request payload.
        
        Request (optional):
        {
            "parameters": {...},   # overrides/extends panel defaults
            "dimensions": [...],   # optional; if omitted, use all model dimensions
            "measures": [...],     # optional; if omitted, use all model measures
            "filters": [...],      # optional
            "time_grain": "day",
            "order_by": [...],
            "limit": 1000
        }
        """
        panel = self.get_object()
        analysis_model = panel.analysis_model
        if not analysis_model:
            return Response({'error': 'Panel has no Analysis Model'}, status=status.HTTP_400_BAD_REQUEST)
        
        from datalab.analytics.analyzer import AnalyzerService, AnalyzerValidationError, AnalyzerExecutionError
        
        body = request.data or {}
        
        # Merge parameters: panel defaults overridden by request
        default_params = panel.default_parameters_json or {}
        override_params = body.get('parameters') or {}
        parameters = {**default_params, **override_params}
        
        # If dimensions/measures not provided, default to all declared in model
        dimensions = body.get('dimensions') or [d['name'] for d in analysis_model.dimensions_json]
        measures = body.get('measures') or [m['name'] for m in analysis_model.measures_json]
        
        exec_request = {
            'parameters': parameters,
            'dimensions': dimensions,
            'measures': measures,
            'filters': body.get('filters', []),
            'time_grain': body.get('time_grain'),
            'order_by': body.get('order_by', []),
            'limit': body.get('limit'),
            'having': body.get('having', []),
        }
        
        analyzer = AnalyzerService()
        try:
            result = analyzer.execute(
                analysis_model=analysis_model,
                request=exec_request,
                user=request.user,
                use_cache=True,
            )
            
            # Map widget ids to resultset (placeholder; front-end will use resultset_id)
            widget_data = {str(w.id): {'resultset_id': result['resultset_id']} for w in panel.widgets.all()}
            
            return Response({
                'panel_id': str(panel.id),
                'analysis_model_id': str(analysis_model.id),
                'resultset_id': result['resultset_id'],
                'row_count': result.get('row_count'),
                'schema': result.get('schema'),
                'data': result.get('data'),
                'metadata': result.get('metadata'),
                'widget_data': widget_data,
            })
        except AnalyzerValidationError as exc:
            return Response({
                'error': 'validation_error',
                'message': str(exc),
                'details': exc.errors,
            }, status=status.HTTP_400_BAD_REQUEST)
        except AnalyzerExecutionError as exc:
            logger.error(f"Panel execution failed: {exc}", exc_info=True)
            return Response({
                'error': 'execution_error',
                'message': str(exc),
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        except Exception as exc:
            logger.error(f"Unexpected panel execution error: {exc}", exc_info=True)
            return Response({
                'error': 'internal_error',
                'message': 'Unexpected error during panel execution',
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    @action(detail=True, methods=['get'])
    def render(self, request, pk=None):
        """Render a panel with all widgets."""
        panel = self.get_object()
        service = PanelService()
        
        try:
            rendered = service.render_panel(panel)
            return Response(rendered)
        except Exception as e:
            logger.error(f"Failed to render panel {panel.id}: {e}", exc_info=True)
            return Response(
                {'error': 'Failed to render panel', 'details': str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class WidgetViewSet(AuthenticatedDataLabView, viewsets.ModelViewSet):
    """ViewSet for Widgets."""
    
    serializer_class = serializers.WidgetSerializer
    
    def get_queryset(self):
        """Get widgets for current tenant."""
        tenant = self.get_tenant(self.request)
        
        # Filter by panel if specified
        panel_id = self.request.query_params.get('panel_id')
        queryset = Widget.objects.filter(tenant=tenant)
        
        if panel_id:
            queryset = queryset.filter(panel_id=panel_id)
        
        return queryset.select_related('panel').order_by('panel', 'order')
    
    def perform_create(self, serializer):
        """Create a new widget."""
        tenant = self.get_tenant(self.request)
        serializer.save(tenant=tenant, created_by=self.request.user)
    
    @action(detail=True, methods=['get'])
    def render(self, request, pk=None):
        """Render a single widget."""
        widget = self.get_object()
        
        try:
            runner = get_widget_runner(widget.widget_type)
            widget_data = runner.render(widget)
            
            return Response({
                'widget': {
                    'id': str(widget.id),
                    'name': widget.name,
                    'type': widget.widget_type,
                },
                'data': widget_data,
            })
        except WidgetRunnerError as e:
            return Response(
                {'error': 'Failed to render widget', 'details': str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )
        except Exception as e:
            logger.error(f"Failed to render widget {widget.id}: {e}", exc_info=True)
            return Response(
                {'error': 'Failed to render widget', 'details': str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
