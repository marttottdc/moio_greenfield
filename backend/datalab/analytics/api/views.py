"""
API Views for Analysis Models and Analyzer.
"""

import logging

from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated

from datalab.analytics.models import AnalysisModel, AnalyzerRun
from datalab.analytics.analyzer import (
    AnalyzerService,
    AnalyzerValidationError,
    AnalyzerExecutionError
)
from datalab.analytics.api.serializers import (
    AnalysisModelSerializer,
    AnalysisModelCreateSerializer,
    AnalyzerRunSerializer,
    AnalyzeRequestSerializer,
    AnalysisModelValidateSerializer
)
from datalab.core.models import Dataset

logger = logging.getLogger(__name__)


class AnalysisModelViewSet(viewsets.ModelViewSet):
    """
    ViewSet for Analysis Model CRUD operations.
    
    Analysis Models are declarative definitions of analytical intent.
    They specify datasets, joins, dimensions, measures, and constraints.
    
    Endpoints:
    - GET    /api/v1/datalab/analysis-models/           - List all models
    - POST   /api/v1/datalab/analysis-models/           - Create new model
    - GET    /api/v1/datalab/analysis-models/{id}/      - Get model details
    - PUT    /api/v1/datalab/analysis-models/{id}/      - Update model (creates new version)
    - DELETE /api/v1/datalab/analysis-models/{id}/      - Delete model
    - POST   /api/v1/datalab/analysis-models/validate/  - Validate without saving
    """
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        queryset = AnalysisModel.objects.filter(
            tenant=self.request.user.current_tenant
        ).select_related('created_by')
        
        # Filter by is_latest by default (unless explicitly requesting all versions)
        show_all_versions = self.request.query_params.get('all_versions', 'false').lower() == 'true'
        if not show_all_versions:
            queryset = queryset.filter(is_latest=True)
        
        # Filter by active status
        active_only = self.request.query_params.get('active_only', 'false').lower() == 'true'
        if active_only:
            queryset = queryset.filter(is_active=True)
        
        return queryset.order_by('-updated_at')
    
    def get_serializer_class(self):
        if self.action in ['create', 'update', 'partial_update']:
            return AnalysisModelCreateSerializer
        return AnalysisModelSerializer
    
    def perform_create(self, serializer):
        serializer.save(
            tenant=self.request.user.current_tenant,
            created_by=self.request.user
        )
    
    def perform_update(self, serializer):
        """
        Update creates a new version of the Analysis Model.
        """
        instance = self.get_object()
        
        # Create new version instead of updating in place
        new_version = instance.version + 1
        
        # Save as new record with incremented version
        serializer.save(
            tenant=self.request.user.current_tenant,
            created_by=self.request.user,
            version=new_version,
            is_latest=True
        )
        
        # Mark old version as not latest
        AnalysisModel.objects.filter(
            tenant=instance.tenant,
            name=instance.name,
            is_latest=True
        ).exclude(version=new_version).update(is_latest=False)
    
    @action(detail=False, methods=['post'])
    def validate(self, request):
        """
        Validate an Analysis Model definition without saving.
        
        POST /api/v1/datalab/analysis-models/validate/
        
        Returns validation result with any warnings.
        """
        serializer = AnalysisModelValidateSerializer(data=request.data)
        
        if not serializer.is_valid():
            return Response({
                'valid': False,
                'errors': serializer.errors
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Use the create serializer for deeper validation
        create_serializer = AnalysisModelCreateSerializer(data=request.data)
        if not create_serializer.is_valid():
            return Response({
                'valid': False,
                'errors': create_serializer.errors
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Additional validation (dataset existence, etc.)
        warnings = self._validate_model_definition(
            create_serializer.validated_data,
            request.user.current_tenant
        )
        
        return Response({
            'valid': True,
            'warnings': warnings
        })
    
    def _validate_model_definition(self, data, tenant) -> list[str]:
        """Validate model definition and return warnings."""
        warnings = []
        
        # Check datasets exist
        for ds_ref in data.get('datasets_json', []):
            try:
                Dataset.objects.get(id=ds_ref['ref'], tenant=tenant)
            except Dataset.DoesNotExist:
                warnings.append(f"Dataset {ds_ref['ref']} (alias: {ds_ref['alias']}) not found")
            except Exception as e:
                warnings.append(f"Error checking dataset {ds_ref['ref']}: {str(e)}")
        
        return warnings
    
    @action(detail=True, methods=['get'])
    def versions(self, request, pk=None):
        """
        List all versions of an Analysis Model.
        
        GET /api/v1/datalab/analysis-models/{id}/versions/
        """
        instance = self.get_object()
        
        versions = AnalysisModel.objects.filter(
            tenant=instance.tenant,
            name=instance.name
        ).order_by('-version')
        
        serializer = AnalysisModelSerializer(versions, many=True)
        return Response(serializer.data)


class AnalyzerViewSet(viewsets.ViewSet):
    """
    ViewSet for Analyzer execution.
    
    The Analyzer is the ONLY component that executes analytics.
    It accepts declarative requests and produces ResultSets.
    
    Endpoints:
    - POST /api/v1/datalab/analyze/ - Execute analysis
    """
    permission_classes = [IsAuthenticated]
    
    def create(self, request):
        """
        Execute an Analysis Model with the given request.
        
        POST /api/v1/datalab/analyze/
        
        Request:
        {
            "analysis_model_id": "uuid",
            "parameters": {...},
            "dimensions": [...],
            "measures": [...],
            "filters": [...],
            "time_grain": "day",
            "order_by": [...],
            "limit": 1000
        }
        
        Response:
        {
            "resultset_id": "uuid",
            "analysis_model_id": "uuid",
            "schema": [...],
            "row_count": 847,
            "data": [...],
            "metadata": {...}
        }
        """
        serializer = AnalyzeRequestSerializer(data=request.data)
        
        if not serializer.is_valid():
            return Response({
                'error': 'validation_error',
                'message': 'Invalid analysis request',
                'details': serializer.errors
            }, status=status.HTTP_400_BAD_REQUEST)
        
        data = serializer.validated_data
        tenant = request.user.current_tenant
        
        # Get Analysis Model
        try:
            analysis_model = AnalysisModel.objects.get(
                id=data['analysis_model_id'],
                tenant=tenant,
                is_active=True
            )
        except AnalysisModel.DoesNotExist:
            return Response({
                'error': 'not_found',
                'message': f"Analysis Model {data['analysis_model_id']} not found or inactive"
            }, status=status.HTTP_404_NOT_FOUND)
        
        # Execute
        analyzer = AnalyzerService()
        
        try:
            # Build request dict (convert serialized filters to dicts)
            exec_request = {
                'parameters': data.get('parameters', {}),
                'dimensions': data.get('dimensions', []),
                'measures': data.get('measures', []),
                'filters': [dict(f) for f in data.get('filters', [])],
                'time_grain': data.get('time_grain'),
                'order_by': [dict(o) for o in data.get('order_by', [])],
                'limit': data.get('limit')
            }
            
            result = analyzer.execute(
                analysis_model=analysis_model,
                request=exec_request,
                user=request.user,
                use_cache=data.get('use_cache', True)
            )
            
            return Response(result)
            
        except AnalyzerValidationError as exc:
            return Response({
                'error': 'validation_error',
                'message': str(exc),
                'details': exc.errors
            }, status=status.HTTP_400_BAD_REQUEST)
            
        except AnalyzerExecutionError as exc:
            logger.error(f"Analyzer execution error: {exc}", exc_info=True)
            return Response({
                'error': 'execution_error',
                'message': str(exc)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        
        except Exception as exc:
            logger.error(f"Unexpected analyzer error: {exc}", exc_info=True)
            return Response({
                'error': 'internal_error',
                'message': 'An unexpected error occurred'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class AnalyzerRunViewSet(viewsets.ReadOnlyModelViewSet):
    """
    ViewSet for viewing Analyzer execution history.
    
    Read-only access to AnalyzerRun records for audit and debugging.
    
    Endpoints:
    - GET /api/v1/datalab/analyzer-runs/       - List runs
    - GET /api/v1/datalab/analyzer-runs/{id}/  - Get run details
    """
    permission_classes = [IsAuthenticated]
    serializer_class = AnalyzerRunSerializer
    
    def get_queryset(self):
        queryset = AnalyzerRun.objects.filter(
            tenant=self.request.user.current_tenant
        ).select_related('analysis_model', 'resultset', 'created_by')
        
        # Filter by analysis_model_id if provided
        model_id = self.request.query_params.get('analysis_model_id')
        if model_id:
            queryset = queryset.filter(analysis_model_id=model_id)
        
        # Filter by status if provided
        status_filter = self.request.query_params.get('status')
        if status_filter:
            queryset = queryset.filter(status=status_filter)
        
        return queryset.order_by('-created_at')
