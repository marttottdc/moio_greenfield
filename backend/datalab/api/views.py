"""
API views for Data Lab endpoints.
"""
from __future__ import annotations

import logging
from uuid import UUID

import boto3
from django.conf import settings
from django.core.files.storage import default_storage
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.views import APIView
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from drf_spectacular.utils import extend_schema, extend_schema_view, OpenApiParameter, OpenApiResponse
from drf_spectacular.types import OpenApiTypes

from datalab.core.models import FileAsset, FileSet, ImportProcess, ImportRun, ResultSet, ResultSetStorage
from datalab.imports.parsers import FileParser, FileParserError
from datalab.imports.pdf_inspector import PDFShapeInspector
from datalab.imports.analyzers.pdf_shape import PdfShapeAnalyzer, PdfShapeAnalyzerError
from datalab.imports.services import ImportExecutor, ImportExecutorError, ImportProcessService
from datalab.imports.validators import ImportContractValidationError
from datalab.imports.interpreters import ShapeInterpreter, ShapeInterpretationError
from portal.authentication import CsrfExemptSessionAuthentication, TenantJWTAAuthentication
from moio_platform.authentication import BearerTokenAuthentication
from rest_framework_simplejwt.authentication import JWTAuthentication
from moio_platform.api_schemas import Tags, STANDARD_ERRORS

from . import serializers

logger = logging.getLogger(__name__)


class AuthenticatedDataLabView(APIView):
    """Base authentication for Data Lab views."""
    authentication_classes = [
        CsrfExemptSessionAuthentication,
        TenantJWTAAuthentication,
        BearerTokenAuthentication,
        JWTAuthentication,
    ]
    permission_classes = [IsAuthenticated]
    
    def get_tenant(self, request):
        """Get tenant from request user."""
        tenant = getattr(request.user, 'tenant', None)
        if tenant is None:
            raise ValidationError({'tenant': 'User must belong to a tenant'})
        return tenant


@extend_schema_view(
    list=extend_schema(
        summary="List file assets",
        description="List all uploaded files for the current tenant.",
        tags=[Tags.DATALAB_FILES],
    ),
    retrieve=extend_schema(
        summary="Get file asset details",
        description="Get metadata for a specific file asset.",
        tags=[Tags.DATALAB_FILES],
    ),
    create=extend_schema(
        summary="Upload file",
        description="Upload a new file (max 100MB). Supports CSV, Excel, and PDF files.",
        tags=[Tags.DATALAB_FILES],
        request={
            "multipart/form-data": {
                "type": "object",
                "required": ["file"],
                "properties": {
                    "file": {"type": "string", "format": "binary", "description": "File to upload"},
                },
            }
        },
    ),
    destroy=extend_schema(
        summary="Delete file asset",
        description="Delete a file asset and its storage.",
        tags=[Tags.DATALAB_FILES],
    ),
)
class FileAssetViewSet(AuthenticatedDataLabView, viewsets.ModelViewSet):
    """ViewSet for FileAsset upload and management."""
    
    serializer_class = serializers.FileAssetSerializer
    
    def get_queryset(self):
        """Get FileAssets for current tenant."""
        tenant = self.get_tenant(self.request)
        return FileAsset.objects.filter(tenant=tenant).order_by('-created_at')
    
    def create(self, request, *args, **kwargs):
        """Upload a file and create FileAsset."""
        tenant = self.get_tenant(request)
        
        if 'file' not in request.FILES:
            return Response(
                {'error': 'file field is required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        uploaded_file = request.FILES['file']
        
        # Validate file size (max 100MB)
        max_size = 100 * 1024 * 1024
        if uploaded_file.size > max_size:
            return Response(
                {'error': f'File size exceeds maximum of {max_size / (1024*1024):.0f}MB'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Generate unique storage key
        import uuid as uuid_lib
        unique_name = f"{uuid_lib.uuid4().hex}_{uploaded_file.name}"
        storage_key = f"datalab/files/{tenant.id}/{unique_name}"
        
        # Save to S3 - save() returns the actual key used (may be normalized)
        try:
            actual_storage_key = default_storage.save(storage_key, uploaded_file)
        except Exception as e:
            logger.error(f"Failed to save file to S3: {e}")
            return Response(
                {'error': 'Failed to save file'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
        
        # Detect metadata
        metadata = {}
        try:
            # Try to detect if it's CSV or Excel
            parser = FileParser()
            if uploaded_file.name.endswith(('.csv', '.txt')):
                metadata['detected_type'] = 'csv'
                # Reset file pointer
                uploaded_file.seek(0)
                try:
                    df = parser.parse_csv(uploaded_file, header_row=0, skip_rows=0)
                    metadata['row_count_estimate'] = len(df)
                    metadata['columns'] = df.columns.tolist()
                except Exception:
                    pass
            elif uploaded_file.name.endswith(('.xlsx', '.xls')):
                metadata['detected_type'] = 'excel'
                # Reset file pointer
                uploaded_file.seek(0)
                try:
                    import pandas as pd
                    excel_file = pd.ExcelFile(uploaded_file)
                    metadata['sheet_names'] = excel_file.sheet_names
                    metadata['sheet_count'] = len(excel_file.sheet_names)
                except Exception:
                    pass
        except Exception:
            pass  # Metadata detection is optional
        
        # Create FileAsset - use the actual storage key returned by save()
        file_asset = FileAsset.objects.create(
            tenant=tenant,
            storage_key=actual_storage_key,
            filename=uploaded_file.name,
            content_type=uploaded_file.content_type or 'application/octet-stream',
            size=uploaded_file.size,
            uploaded_by=request.user,
            metadata=metadata
        )
        
        serializer = self.get_serializer(file_asset)
        return Response(serializer.data, status=status.HTTP_201_CREATED)
    
    @extend_schema(
        summary="Download file",
        description="Get a presigned URL to download the file.",
        tags=[Tags.DATALAB_FILES],
        responses={
            200: OpenApiResponse(description="Presigned download URL"),
            404: OpenApiResponse(description="File not found in storage"),
        },
    )
    @action(detail=True, methods=['get'])
    def download(self, request, pk=None):
        """Download the actual file content."""
        file_asset = self.get_object()
        
        try:
            # Check if file exists in storage
            if not default_storage.exists(file_asset.storage_key):
                logger.error(
                    f"File not found in storage: {file_asset.storage_key} "
                    f"(FileAsset ID: {file_asset.id})"
                )
                return Response(
                    {
                        'error': 'File not found in storage',
                        'storage_key': file_asset.storage_key,
                        'file_id': str(file_asset.id)
                    },
                    status=status.HTTP_404_NOT_FOUND
                )
            
            # Get file from S3
            file_obj = default_storage.open(file_asset.storage_key, 'rb')
            file_content = file_obj.read()
            file_obj.close()
            
            # Return file with appropriate headers
            from django.http import HttpResponse
            response = HttpResponse(file_content, content_type=file_asset.content_type)
            response['Content-Disposition'] = f'attachment; filename="{file_asset.filename}"'
            response['Content-Length'] = len(file_content)
            return response
            
        except Exception as e:
            logger.error(
                f"Failed to download file {file_asset.id} "
                f"(storage_key: {file_asset.storage_key}): {e}",
                exc_info=True
            )
            return Response(
                {
                    'error': 'Failed to download file',
                    'details': str(e),
                    'storage_key': file_asset.storage_key
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class FileSetViewSet(AuthenticatedDataLabView, viewsets.ModelViewSet):
    """ViewSet for FileSet management."""
    
    serializer_class = serializers.FileSetSerializer
    
    def get_queryset(self):
        """Get FileSets for current tenant."""
        tenant = self.get_tenant(self.request)
        return FileSet.objects.filter(tenant=tenant).prefetch_related('files').order_by('-created_at')
    
    def perform_create(self, serializer):
        """Create FileSet with tenant."""
        serializer.save(tenant=self.get_tenant(self.request))
    
    @action(detail=True, methods=['post'])
    def add_files(self, request, pk=None):
        """Add files to FileSet."""
        fileset = self.get_object()
        tenant = self.get_tenant(request)
        
        file_ids = request.data.get('file_ids', [])
        if not file_ids:
            return Response(
                {'error': 'file_ids is required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Validate files belong to tenant
        files = FileAsset.objects.filter(id__in=file_ids, tenant=tenant)
        if files.count() != len(file_ids):
            return Response(
                {'error': 'Some files not found or belong to different tenant'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Add files to FileSet
        fileset.files.add(*files)
        
        serializer = self.get_serializer(fileset)
        return Response(serializer.data)


class ImportViewSet(AuthenticatedDataLabView, viewsets.ViewSet):
    """ViewSet for import operations (preview and execute)."""
    
    executor = ImportExecutor()
    parser = FileParser()
    shape_inspector = PDFShapeInspector()
    pdf_shape_analyzer = PdfShapeAnalyzer()
    
    @action(detail=False, methods=['post'])
    def preview(self, request):
        """Preview import without executing."""
        tenant = self.get_tenant(request)
        
        serializer = serializers.ImportPreviewRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        source = serializer.validated_data['source']
        contract_json = serializer.validated_data['contract_json']
        
        try:
            # Validate contract using Pydantic
            from datalab.imports.contracts import ImportContractV1
            try:
                ImportContractV1.model_validate(contract_json)
            except Exception as e:
                return Response(
                    {'error': 'Invalid contract', 'details': str(e)},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # Get file(s) and parse
            if 'file_id' in source:
                file_asset = FileAsset.objects.get(id=source['file_id'], tenant=tenant)
                df = self.executor._parse_file(file_asset, contract_json)
            elif 'fileset_id' in source:
                fileset = FileSet.objects.get(id=source['fileset_id'], tenant=tenant)
                # Parse first file for preview
                first_file = fileset.files.first()
                if not first_file:
                    return Response(
                        {'error': 'FileSet has no files'},
                        status=status.HTTP_400_BAD_REQUEST
                    )
                df = self.executor._parse_file(first_file, contract_json)
            else:
                return Response(
                    {'error': 'Invalid source'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # Detect schema
            detected_schema = self.parser.detect_schema(df)
            
            # Get sample rows
            sample_rows = df.head(100).to_dict(orient='records')
            
            # Estimate row count
            row_count_estimate = len(df)
            
            # Generate warnings (simplified)
            warnings = []
            # TODO: Add more sophisticated warnings
            
            response_data = {
                'detected_schema': detected_schema,
                'sample_rows': sample_rows,
                'row_count_estimate': row_count_estimate,
                'warnings': warnings
            }
            
            response_serializer = serializers.ImportPreviewResponseSerializer(data=response_data)
            response_serializer.is_valid(raise_exception=True)
            
            return Response(response_serializer.data)
            
        except FileAsset.DoesNotExist:
            return Response(
                {'error': 'File not found'},
                status=status.HTTP_404_NOT_FOUND
            )
        except FileSet.DoesNotExist:
            return Response(
                {'error': 'FileSet not found'},
                status=status.HTTP_404_NOT_FOUND
            )
        except (FileParserError, ImportContractValidationError) as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )
        except Exception as e:
            logger.error(f"Preview error: {e}", exc_info=True)
            return Response(
                {'error': 'Preview failed', 'details': str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @action(detail=False, methods=['post'])
    def execute(self, request):
        """Execute import (backward compatibility bridge)."""
        tenant = self.get_tenant(request)

        serializer = serializers.ImportExecuteRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        source = serializer.validated_data['source']
        contract_json = serializer.validated_data['contract_json']
        materialize = serializer.validated_data.get('materialize', False)
        rebuild = serializer.validated_data.get('rebuild', False)
        accumulation = serializer.validated_data.get('accumulation')
        import_data_as_json = serializer.validated_data.get('import_data_as_json', False)

        try:
            # Use v3.1 backward compatibility bridge
            process_service = ImportProcessService()
            resultset = process_service.execute_legacy_import(
                source=source,
                contract_json=contract_json,
                materialize=materialize,
                rebuild=rebuild,
                accumulation=accumulation,
                user=request.user,
                import_data_as_json=import_data_as_json
            )

            # Get snapshot_id if FileSet
            snapshot_id = None
            if 'fileset_id' in source:
                fileset = FileSet.objects.get(id=source['fileset_id'], tenant=tenant)
                if fileset.last_snapshot:
                    snapshot_id = fileset.last_snapshot.id

            response_data = {
                'resultset_id': resultset.id,
                'schema': resultset.schema_json,
                'row_count': resultset.row_count,
                'preview': resultset.preview_json,
            }
            if snapshot_id:
                response_data['snapshot_id'] = snapshot_id

            response_serializer = serializers.ImportExecuteResponseSerializer(data=response_data)
            response_serializer.is_valid(raise_exception=True)

            return Response(response_serializer.data, status=status.HTTP_201_CREATED)

        except ImportExecutorError as e:
            return Response(
                {'error': 'Import execution failed', 'details': str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )
        except Exception as e:
            logger.error(f"Import execution error: {e}", exc_info=True)
            return Response(
                {'error': 'Import execution failed', 'details': str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    @action(detail=False, methods=['post'], url_path='inspect-shape')
    def inspect_shape(self, request):
        """
        Inspect file shape (supports PDF via PdfShapeAnalyzer).
        """
        tenant = self.get_tenant(request)

        serializer = serializers.ShapeInspectRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        source = serializer.validated_data['source']

        try:
            file_asset = FileAsset.objects.get(id=source['file_id'], tenant=tenant)
        except FileAsset.DoesNotExist:
            return Response(
                {'error': 'File not found'},
                status=status.HTTP_404_NOT_FOUND
            )

        try:
            with default_storage.open(file_asset.storage_key, 'rb') as file_obj:
                result = self.pdf_shape_analyzer.analyze(file_obj)
                from datalab.core.serialization import serialize_for_json
                result = serialize_for_json(result)
        except PdfShapeAnalyzerError as e:
            return Response(
                {'error': 'Shape inspection failed', 'details': str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )
        except Exception as e:
            logger.error(f"Shape inspection failed: {e}", exc_info=True)
            return Response(
                {'error': 'Shape inspection failed', 'details': str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

        response_serializer = serializers.ShapeInspectResponseSerializer(data=result)
        response_serializer.is_valid(raise_exception=True)
        return Response(response_serializer.data)


class ResultSetViewSet(AuthenticatedDataLabView, 
                       mixins.RetrieveModelMixin,
                       mixins.ListModelMixin, 
                       mixins.UpdateModelMixin,
                       mixins.DestroyModelMixin,
                       viewsets.GenericViewSet):
    """ViewSet for ResultSet viewing, updating (name/expires_at), deletion, and materialization."""
    
    serializer_class = serializers.ResultSetSerializer
    
    def retrieve(self, request, *args, **kwargs):
        """Enforce fencing: only durable or analyzer ResultSets are accessible."""
        resultset = self.get_object()
        if not resultset.is_accessible_for_presentation():
            return Response(
                {'error': 'ResultSet is fenced (ephemeral and not from Analyzer)'},
                status=status.HTTP_403_FORBIDDEN
            )
        return super().retrieve(request, *args, **kwargs)
    
    def get_queryset(self):
        """Get ResultSets for current tenant."""
        tenant = self.get_tenant(self.request)
        return ResultSet.objects.filter(tenant=tenant).order_by('-created_at')
    
    @action(detail=True, methods=['post'])
    def materialize(self, request, pk=None):
        """Materialize ResultSet as Parquet in S3."""
        resultset = self.get_object()
        
        if resultset.storage == ResultSetStorage.PARQUET.value:
            return Response(
                {'message': 'ResultSet already materialized'},
                status=status.HTTP_200_OK
            )
        
        try:
            from datalab.core.storage import get_storage
            storage = get_storage()
            
            # Load from memory (would need to store full data somewhere)
            # For now, this is a limitation - we'd need to keep the full DataFrame
            # or reconstruct from preview (limited)
            return Response(
                {'error': 'Materialization from memory not yet supported. Use materialize=true during import.'},
                status=status.HTTP_400_BAD_REQUEST
            )
            
        except Exception as e:
            logger.error(f"Materialization error: {e}", exc_info=True)
            return Response(
                {'error': 'Materialization failed', 'details': str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


# ===== v3.1 ImportProcess Views =====

class ImportProcessViewSet(AuthenticatedDataLabView, viewsets.ModelViewSet):
    """ViewSet for ImportProcess CRUD operations."""

    serializer_class = serializers.ImportProcessSerializer

    def get_queryset(self):
        """Get ImportProcesses for current tenant."""
        tenant = self.get_tenant(self.request)
        return ImportProcess.objects.filter(tenant=tenant).order_by('-created_at')

    def get_serializer_class(self):
        """Return appropriate serializer based on action."""
        if self.action == 'create':
            return serializers.ImportProcessCreateSerializer
        return serializers.ImportProcessSerializer

    def perform_create(self, serializer):
        """Create ImportProcess with tenant."""
        serializer.save(tenant=self.get_tenant(self.request))

    @action(detail=True, methods=['post'])
    def run(self, request, pk=None):
        """Run an ImportProcess against a RawDataset."""
        import_process = self.get_object()

        serializer = serializers.ImportProcessRunSerializer(
            data=request.data,
            context={'request': request, 'import_process': import_process}
        )
        serializer.is_valid(raise_exception=True)
        import_run = serializer.save()

        response_serializer = serializers.ImportRunSerializer(import_run)
        return Response(response_serializer.data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['post'])
    def clone(self, request, pk=None):
        """Clone an ImportProcess to create a new version."""
        import_process = self.get_object()

        serializer = serializers.ImportProcessCloneSerializer(
            data=request.data,
            context={'request': request, 'import_process': import_process}
        )
        serializer.is_valid(raise_exception=True)
        cloned_process = serializer.save()

        response_serializer = serializers.ImportProcessSerializer(cloned_process)
        return Response(response_serializer.data, status=status.HTTP_201_CREATED)

    @action(detail=False, methods=['post'], url_path='inspect-shape')
    def inspect_shape(self, request):
        """Inspect shape of a file for ImportProcess creation."""
        tenant = self.get_tenant(request)

        serializer = serializers.FileAssetSerializer(data={'file_ids': [request.data.get('file_id')]})
        if not request.data.get('file_id'):
            return Response(
                {'error': 'file_id is required'},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            file_asset = FileAsset.objects.get(
                id=request.data['file_id'],
                tenant=tenant
            )
        except FileAsset.DoesNotExist:
            return Response(
                {'error': 'File not found'},
                status=status.HTTP_404_NOT_FOUND
            )

        file_type = request.data.get('file_type')
        if not file_type or file_type not in ['csv', 'excel', 'pdf']:
            return Response(
                {'error': 'file_type is required and must be csv, excel, or pdf'},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            from datalab.imports.services import ImportProcessService
            service = ImportProcessService()

            from django.core.files.storage import default_storage
            with default_storage.open(file_asset.storage_key, 'rb') as file_obj:
                shape_info = service.shape_inspector.inspect(
                    file_obj,
                    file_type,
                    file_asset.filename
                )

            return Response(shape_info)

        except Exception as e:
            logger.error(f"Shape inspection failed: {e}", exc_info=True)
            return Response(
                {'error': f'Shape inspection failed: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    @action(detail=False, methods=['post'], url_path='interpret-shape')
    def interpret_shape(self, request):
        """Interpret shape inspection results using LLM."""
        tenant = self.get_tenant(request)

        # Get shape inspection data from request
        shape_inspection = request.data.get('shape_inspection')
        if not shape_inspection:
            return Response(
                {'error': 'shape_inspection is required'},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            from portal.models import TenantConfiguration
            from django.shortcuts import get_object_or_404
            
            tenant_config = get_object_or_404(TenantConfiguration, tenant=tenant)
            
            interpreter = ShapeInterpreter(tenant_config)
            interpretation = interpreter.interpret(shape_inspection)
            
            return Response(interpretation)

        except ShapeInterpretationError as e:
            logger.error(f"Shape interpretation failed: {e}", exc_info=True)
            return Response(
                {'error': f'Shape interpretation failed: {str(e)}'},
                status=status.HTTP_400_BAD_REQUEST
            )
        except Exception as e:
            logger.error(f"Shape interpretation error: {e}", exc_info=True)
            return Response(
                {'error': f'Shape interpretation error: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class ImportRunViewSet(AuthenticatedDataLabView, viewsets.ReadOnlyModelViewSet):
    """ViewSet for viewing ImportRuns."""

    serializer_class = serializers.ImportRunSerializer

    def get_queryset(self):
        """Get ImportRuns for current tenant."""
        tenant = self.get_tenant(self.request)
        return ImportRun.objects.filter(tenant=tenant).select_related(
            'import_process', 'raw_dataset'
        ).order_by('-created_at')


# ===== v3.2 Dataset & DatasetVersion Views =====

class DataSourceViewSet(AuthenticatedDataLabView, viewsets.ReadOnlyModelViewSet):
    """ViewSet for DataSource operations."""

    serializer_class = serializers.DataSourceSerializer

    def get_queryset(self):
        tenant = self.get_tenant(self.request)
        return DataSource.objects.filter(tenant=tenant).order_by('-created_at')

    def get_serializer_class(self):
        return serializers.DataSourceSerializer


class DatasetViewSet(AuthenticatedDataLabView, viewsets.ModelViewSet):
    """ViewSet for Dataset CRUD operations."""

    serializer_class = serializers.DatasetSerializer

    def get_queryset(self):
        tenant = self.get_tenant(self.request)
        return Dataset.objects.filter(tenant=tenant).order_by('-updated_at')

    def get_serializer_class(self):
        if self.action == 'create':
            return serializers.DatasetCreateSerializer
        return serializers.DatasetSerializer

    def perform_create(self, serializer):
        serializer.save(
            tenant=self.get_tenant(self.request),
            created_by=self.request.user
        )

    @action(detail=True, methods=['post'])
    def create_version(self, request, pk=None):
        """Create a new DatasetVersion from a ResultSet."""
        dataset = self.get_object()

        serializer = serializers.DatasetVersionCreateSerializer(
            data=request.data,
            context={'request': request, 'dataset': dataset}
        )
        serializer.is_valid(raise_exception=True)

        version = serializer.save()
        return Response(
            serializers.DatasetVersionSerializer(version).data,
            status=status.HTTP_201_CREATED
        )

    @action(detail=True, methods=['post'])
    def promote_version(self, request, pk=None):
        """Promote a DatasetVersion to current."""
        dataset = self.get_object()

        serializer = serializers.DatasetPromoteVersionSerializer(
            data=request.data,
            context={'request': request, 'dataset': dataset}
        )
        serializer.is_valid(raise_exception=True)

        version = serializer.save()
        return Response(
            serializers.DatasetVersionSerializer(version).data,
            status=status.HTTP_200_OK
        )


class DatasetVersionViewSet(AuthenticatedDataLabView, viewsets.ReadOnlyModelViewSet):
    """ViewSet for DatasetVersion operations."""

    serializer_class = serializers.DatasetVersionSerializer

    def get_queryset(self):
        tenant = self.get_tenant(self.request)
        return DatasetVersion.objects.filter(tenant=tenant).select_related(
            'dataset', 'result_set', 'created_by'
        ).order_by('-created_at')
