"""
Serializers for Data Lab API endpoints.
"""
from __future__ import annotations

from rest_framework import serializers
from rest_framework.exceptions import ValidationError

from datalab.core.models import (
    AccumulationLog,
    DataSource,
    Dataset,
    DatasetVersion,
    FileAsset,
    FileSet,
    ImportProcess,
    ImportRun,
    ResultSet,
    Snapshot,
)
from datalab.crm_sources.models import CRMView
from datalab.panels.models import Panel, Widget


class FileAssetSerializer(serializers.ModelSerializer):
    """Serializer for FileAsset."""
    
    class Meta:
        model = FileAsset
        fields = [
            'id',
            'filename',
            'content_type',
            'size',
            'metadata',
            'uploaded_by',
            'created_at',
        ]
        read_only_fields = ['id', 'uploaded_by', 'created_at']


class FileSetSerializer(serializers.ModelSerializer):
    """Serializer for FileSet."""
    
    files = FileAssetSerializer(many=True, read_only=True)
    file_ids = serializers.ListField(
        child=serializers.UUIDField(),
        write_only=True,
        required=False
    )
    file_count = serializers.IntegerField(source='files.count', read_only=True)
    
    class Meta:
        model = FileSet
        fields = [
            'id',
            'name',
            'description',
            'files',
            'file_ids',
            'file_count',
            'schema_hint',
            'last_snapshot',
            'created_at',
            'updated_at',
        ]
        read_only_fields = ['id', 'last_snapshot', 'created_at', 'updated_at']
    
    def create(self, validated_data):
        """Create FileSet and associate files."""
        file_ids = validated_data.pop('file_ids', [])
        tenant = validated_data['tenant']
        
        fileset = FileSet.objects.create(**validated_data)
        
        if file_ids:
            files = FileAsset.objects.filter(id__in=file_ids, tenant=tenant)
            fileset.files.set(files)
        
        return fileset
    
    def update(self, instance, validated_data):
        """Update FileSet and files if provided."""
        file_ids = validated_data.pop('file_ids', None)
        
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()
        
        if file_ids is not None:
            files = FileAsset.objects.filter(id__in=file_ids, tenant=instance.tenant)
            instance.files.set(files)
        
        return instance


class ResultSetSerializer(serializers.ModelSerializer):
    """Serializer for ResultSet."""
    
    created_by_email = serializers.EmailField(source='created_by.email', read_only=True)
    
    class Meta:
        model = ResultSet
        fields = [
            'id',
            'name',
            'origin',
            'schema_json',
            'row_count',
            'storage',
            'is_json_object',
            'preview_json',
            'lineage_json',
            'created_by',
            'created_by_email',
            'created_at',
            'expires_at',
        ]
        read_only_fields = [
            'id',
            'origin',
            'schema_json',
            'row_count',
            'storage',
            'storage_key',
            'is_json_object',
            'preview_json',
            'lineage_json',
            'created_by',
            'created_at',
        ]


class SnapshotSerializer(serializers.ModelSerializer):
    """Serializer for Snapshot."""
    
    resultset = ResultSetSerializer(read_only=True)
    created_by_email = serializers.EmailField(source='created_by.email', read_only=True)
    
    class Meta:
        model = Snapshot
        fields = [
            'id',
            'name',
            'version',
            'resultset',
            'description',
            'fileset',
            'created_by',
            'created_by_email',
            'created_at',
        ]
        read_only_fields = ['id', 'created_by', 'created_at']


class ImportPreviewRequestSerializer(serializers.Serializer):
    """Serializer for import preview request."""
    
    source = serializers.DictField(
        help_text="{'file_id': UUID} or {'fileset_id': UUID}"
    )
    contract_json = serializers.DictField(
        help_text="Complete ImportContract JSON"
    )
    
    def validate_source(self, value):
        """Validate source has either file_id or fileset_id."""
        if 'file_id' not in value and 'fileset_id' not in value:
            raise ValidationError("source must have 'file_id' or 'fileset_id'")
        if 'file_id' in value and 'fileset_id' in value:
            raise ValidationError("source cannot have both 'file_id' and 'fileset_id'")
        return value


class ImportPreviewResponseSerializer(serializers.Serializer):
    """Serializer for import preview response."""
    
    detected_schema = serializers.ListField(
        child=serializers.DictField(),
        help_text="Detected column schema"
    )
    sample_rows = serializers.ListField(
        child=serializers.DictField(),
        help_text="Sample rows (limited)"
    )
    row_count_estimate = serializers.IntegerField(
        help_text="Estimated total row count"
    )
    warnings = serializers.ListField(
        child=serializers.CharField(),
        required=False,
        help_text="Warnings about the data"
    )


class ImportExecuteRequestSerializer(serializers.Serializer):
    """Serializer for import execute request."""
    
    source = serializers.DictField(
        help_text="{'file_id': UUID} or {'fileset_id': UUID}"
    )
    contract_json = serializers.DictField(
        help_text="Complete ImportContract JSON"
    )
    materialize = serializers.BooleanField(
        default=False,
        help_text="Force materialization as Parquet"
    )
    import_data_as_json = serializers.BooleanField(
        default=False,
        help_text="If True, return data as JSON Object instead of DataFrame"
    )
    rebuild = serializers.BooleanField(
        default=False,
        help_text="Process all files from scratch (ignore accumulation)"
    )
    accumulation = serializers.DictField(
        required=False,
        help_text="Accumulation config: {'strategy': 'append|merge', 'dedupe_keys': [...]}"
    )
    
    def validate_source(self, value):
        """Validate source has either file_id or fileset_id."""
        if 'file_id' not in value and 'fileset_id' not in value:
            raise ValidationError("source must have 'file_id' or 'fileset_id'")
        if 'file_id' in value and 'fileset_id' in value:
            raise ValidationError("source cannot have both 'file_id' and 'fileset_id'")
        return value


class ImportExecuteResponseSerializer(serializers.Serializer):
    """Serializer for import execute response."""
    
    resultset_id = serializers.UUIDField()
    schema = serializers.ListField(child=serializers.DictField())
    row_count = serializers.IntegerField()
    preview = serializers.ListField(child=serializers.DictField())
    snapshot_id = serializers.UUIDField(required=False, allow_null=True)


class ShapeInspectRequestSerializer(serializers.Serializer):
    """Serializer for shape inspection (PDF-focused)."""

    source = serializers.DictField(
        help_text="{'file_id': UUID}"
    )

    def validate_source(self, value):
        """Validate source has file_id."""
        if 'file_id' not in value:
            raise ValidationError("source must have 'file_id'")
        return value


class ShapeInspectResponseSerializer(serializers.Serializer):
    """Serializer for shape inspection response."""

    fingerprint = serializers.CharField()
    description = serializers.DictField()


class CRMViewSerializer(serializers.ModelSerializer):
    """Serializer for CRMView."""
    
    class Meta:
        model = CRMView
        fields = [
            'id',
            'key',
            'label',
            'description',
            'schema_json',
            'allowed_filters_json',
            'default_filters_json',
            'is_active',
            'created_at',
        ]
        read_only_fields = ['id', 'created_at']


class CRMQueryRequestSerializer(serializers.Serializer):
    """Serializer for CRM query request."""
    
    view_key = serializers.CharField(help_text="CRM View key (e.g., 'crm.deals.active')")
    filters = serializers.DictField(
        required=False,
        default=dict,
        help_text="Filters to apply: {'status': 'won', 'date_from': '2024-01-01', ...}"
    )
    projection = serializers.ListField(
        child=serializers.CharField(),
        required=False,
        help_text="Optional: list of columns to return (not yet implemented)"
    )
    limit = serializers.IntegerField(
        required=False,
        min_value=1,
        max_value=100000,
        help_text="Optional: limit number of rows returned"
    )
    materialize = serializers.BooleanField(
        default=False,
        help_text="Force materialization as Parquet"
    )


class CRMQueryResponseSerializer(serializers.Serializer):
    """Serializer for CRM query response."""
    
    resultset_id = serializers.UUIDField()
    schema = serializers.ListField(child=serializers.DictField())
    row_count = serializers.IntegerField()
    preview = serializers.ListField(child=serializers.DictField())


class ExecuteQuerySpecSerializer(serializers.Serializer):
    """Nested serializer for query in execute request."""
    type = serializers.ChoiceField(choices=["crm_view", "sql"])
    view_key = serializers.CharField(required=False, allow_blank=True)
    filters = serializers.DictField(required=False, default=dict)
    sql = serializers.CharField(required=False, allow_blank=True)
    params = serializers.ListField(required=False, default=list)

    def validate(self, attrs):
        if attrs["type"] == "crm_view" and not attrs.get("view_key"):
            raise ValidationError({"view_key": "Required for type 'crm_view'"})
        if attrs["type"] == "sql" and not attrs.get("sql"):
            raise ValidationError({"sql": "Required for type 'sql'"})
        return attrs


class ExecuteRequestSerializer(serializers.Serializer):
    """Request for Data Lab execute (query + optional post_process, or snippet)."""
    query = ExecuteQuerySpecSerializer(required=False)
    post_process_code = serializers.CharField(required=False, allow_blank=True)
    code = serializers.CharField(required=False, allow_blank=True)
    persist = serializers.BooleanField(
        default=False,
        help_text="If True and result is a list of rows, save as ResultSet and return resultset_id",
    )

    def validate(self, attrs):
        has_query = attrs.get("query") is not None
        has_code = bool(attrs.get("code", "").strip())
        if has_query and has_code:
            raise ValidationError("Provide either 'query' (with optional post_process_code) or 'code', not both.")
        if not has_query and not has_code:
            raise ValidationError("Provide 'query' or 'code'.")
        return attrs


class ExecuteResponseSerializer(serializers.Serializer):
    """Response from Data Lab execute."""
    result = serializers.JSONField(help_text="Query result or snippet/post_process output")
    row_count = serializers.IntegerField(required=False, help_text="Number of rows when result is a list")
    resultset_id = serializers.UUIDField(required=False, help_text="When persist=True, ID of created ResultSet")


class PanelSerializer(serializers.ModelSerializer):
    """Serializer for Panel."""
    
    created_by_email = serializers.EmailField(source='created_by.email', read_only=True)
    widget_count = serializers.IntegerField(source='widgets.count', read_only=True)
    
    class Meta:
        model = Panel
        fields = [
            'id',
            'name',
            'description',
            'layout_json',
            'is_public',
            'shared_with_roles',
            'created_by',
            'created_by_email',
            'widget_count',
            'created_at',
            'updated_at',
        ]
        read_only_fields = ['id', 'created_by', 'created_at', 'updated_at']


class WidgetSerializer(serializers.ModelSerializer):
    """Serializer for Widget."""

    created_by_email = serializers.EmailField(source='created_by.email', read_only=True)
    panel_name = serializers.CharField(source='panel.name', read_only=True)

    class Meta:
        model = Widget
        fields = [
            'id',
            'panel',
            'panel_name',
            'name',
            'widget_type',
            'datasource_id',
            'config_json',
            'position_x',
            'position_y',
            'width',
            'height',
            'is_visible',
            'order',
            'created_by',
            'created_by_email',
            'created_at',
            'updated_at',
        ]
        read_only_fields = ['id', 'created_by', 'created_at', 'updated_at']


# ===== v3.1 ImportProcess Serializers =====

class ImportProcessSerializer(serializers.ModelSerializer):
    """Serializer for ImportProcess."""

    class Meta:
        model = ImportProcess
        fields = [
            'id',
            'name',
            'file_type',
            'import_data_as_json',
            'shape_fingerprint',
            'shape_description',
            'structural_units',
            'semantic_derivations',
            'contract_json',  # Complete import contract (parser + mapping)
            'version',
            'is_active',
            'created_at',
            'updated_at',
        ]
        read_only_fields = ['id', 'version', 'shape_fingerprint', 'created_at', 'updated_at']


class ImportProcessCreateSerializer(serializers.Serializer):
    """Serializer for creating ImportProcess."""

    name = serializers.CharField(max_length=200)
    file_type = serializers.ChoiceField(choices=['csv', 'excel', 'pdf'])
    file_id = serializers.UUIDField(write_only=True)  # File to inspect for shape
    import_data_as_json = serializers.BooleanField(default=False, required=False)

    def create(self, validated_data):
        from datalab.imports.services import ImportProcessService
        from datalab.core.models import FileAsset

        tenant = self.context['request'].user.tenant
        file_asset = FileAsset.objects.get(
            id=validated_data['file_id'],
            tenant=tenant
        )

        service = ImportProcessService()
        # Inspect shape
        from django.core.files.storage import default_storage
        with default_storage.open(file_asset.storage_key, 'rb') as file_obj:
            shape_info = service.shape_inspector.inspect(
                file_obj,
                validated_data['file_type'],
                file_asset.filename
            )

        # Create process
        return service.create_import_process(
            tenant=tenant,
            name=validated_data['name'],
            file_type=validated_data['file_type'],
            shape_fingerprint=shape_info['fingerprint'],
            shape_description=shape_info['description'],
            import_data_as_json=validated_data.get('import_data_as_json', False),
        )

    def to_representation(self, instance):
        # Return the standard ImportProcess representation (no file_id)
        from datalab.api.serializers import ImportProcessSerializer
        return ImportProcessSerializer(instance, context=self.context).data


class ImportRunSerializer(serializers.ModelSerializer):
    """Serializer for ImportRun."""

    import_process_name = serializers.CharField(source='import_process.name', read_only=True)
    raw_dataset_filename = serializers.CharField(source='raw_dataset.filename', read_only=True)
    resultsets = serializers.SerializerMethodField()

    class Meta:
        model = ImportRun
        fields = [
            'id',
            'import_process',
            'import_process_name',
            'raw_dataset',
            'raw_dataset_filename',
            'shape_match',
            'status',
            'error_message',  # Error details if failed
            'resultset_ids',
            'resultsets',  # Inline ResultSet data
            'created_at',
        ]
        read_only_fields = ['id', 'shape_match', 'status', 'error_message', 'resultset_ids', 'created_at']

    def get_resultsets(self, obj):
        """Include inline ResultSet data for convenience."""
        if not obj.resultset_ids:
            return []
        
        resultsets = ResultSet.objects.filter(id__in=obj.resultset_ids)
        return [
            {
                'id': str(rs.id),
                'name': rs.name,
                'schema_json': rs.schema_json,
                'row_count': rs.row_count,
                'preview_json': rs.preview_json,
            }
            for rs in resultsets
        ]


class ImportProcessRunSerializer(serializers.Serializer):
    """Serializer for running an ImportProcess."""

    raw_dataset_id = serializers.UUIDField()

    def create(self, validated_data):
        from datalab.imports.services import ImportProcessService
        from datalab.core.models import FileAsset

        import_process = self.context['import_process']
        tenant = self.context['request'].user.tenant

        raw_dataset = FileAsset.objects.get(
            id=validated_data['raw_dataset_id'],
            tenant=tenant
        )

        service = ImportProcessService()
        user = self.context['request'].user

        return service.run_import_process(import_process, raw_dataset, user)


class ImportProcessCloneSerializer(serializers.Serializer):
    """Serializer for cloning an ImportProcess."""

    name = serializers.CharField(max_length=200, required=False)

    def create(self, validated_data):
        from datalab.imports.services import ImportProcessService

        import_process = self.context['import_process']
        service = ImportProcessService()
        user = self.context['request'].user

        return service.clone_import_process(
            import_process,
            new_name=validated_data.get('name'),
            user=user
        )


# ===== v3.2 Dataset & DatasetVersion Serializers =====

class DataSourceSerializer(serializers.ModelSerializer):
    """Base serializer for DataSource."""

    type_display = serializers.CharField(source='get_type_display', read_only=True)

    class Meta:
        model = DataSource
        fields = [
            'id', 'name', 'type', 'type_display', 'ref_id', 'description',
            'schema_json', 'acl_json', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']


class DatasetSerializer(serializers.ModelSerializer):
    """Serializer for Dataset."""

    current_version_id = serializers.UUIDField(source='current_version.id', read_only=True)
    created_by_email = serializers.EmailField(source='created_by.email', read_only=True)

    class Meta:
        model = Dataset
        fields = [
            'id', 'name', 'description', 'current_version_id',
            'created_by', 'created_by_email', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_by', 'created_at', 'updated_at']


class DatasetVersionSerializer(serializers.ModelSerializer):
    """Serializer for DatasetVersion."""

    dataset_name = serializers.CharField(source='dataset.name', read_only=True)
    created_by_email = serializers.EmailField(source='created_by.email', read_only=True)

    class Meta:
        model = DatasetVersion
        fields = [
            'id', 'dataset', 'dataset_name', 'version_number', 'result_set',
            'description', 'is_current', 'created_by', 'created_by_email', 'created_at'
        ]
        read_only_fields = ['id', 'version_number', 'created_by', 'created_at']


class DatasetCreateSerializer(serializers.Serializer):
    """Serializer for creating a Dataset."""

    name = serializers.CharField(max_length=200)
    description = serializers.CharField(required=False, allow_blank=True)


class DatasetVersionCreateSerializer(serializers.Serializer):
    """Serializer for creating a DatasetVersion from a ResultSet."""

    result_set_id = serializers.UUIDField()
    description = serializers.CharField(required=False, allow_blank=True)

    def create(self, validated_data):
        from datalab.core.models import ResultSet, DatasetVersion

        tenant = self.context['request'].user.tenant
        dataset = self.context['dataset']
        result_set = ResultSet.objects.get(
            id=validated_data['result_set_id'],
            tenant=tenant,
            durability='durable'
        )

        # Calculate next version number
        last_version = DatasetVersion.objects.filter(dataset=dataset).order_by('-version_number').first()
        version_number = (last_version.version_number + 1) if last_version else 1

        # Create version
        version = DatasetVersion.objects.create(
            tenant=tenant,
            dataset=dataset,
            version_number=version_number,
            result_set=result_set,
            description=validated_data.get('description', ''),
            created_by=self.context['request'].user
        )

        # Update ResultSet reference
        result_set.dataset_version = version
        result_set.save(update_fields=['dataset_version'])

        return version


class DatasetPromoteVersionSerializer(serializers.Serializer):
    """Serializer for promoting a DatasetVersion to current."""

    version_id = serializers.UUIDField()

    def create(self, validated_data):
        from datalab.core.models import DatasetVersion

        tenant = self.context['request'].user.tenant
        dataset = self.context['dataset']

        version = DatasetVersion.objects.get(
            id=validated_data['version_id'],
            dataset=dataset,
            tenant=tenant
        )

        # Promote this version to current
        version.is_current = True
        version.save()

        # Update dataset current_version pointer
        dataset.current_version = version
        dataset.save(update_fields=['current_version'])

        return version
