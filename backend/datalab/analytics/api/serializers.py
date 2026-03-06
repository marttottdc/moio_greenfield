"""
Serializers for Analysis Models and Analyzer API.
"""

from rest_framework import serializers

from datalab.analytics.models import AnalysisModel, AnalyzerRun


class AnalysisModelSerializer(serializers.ModelSerializer):
    """Serializer for reading Analysis Models."""
    
    created_by_name = serializers.SerializerMethodField()
    
    class Meta:
        model = AnalysisModel
        fields = [
            'id', 'name', 'description', 'version',
            'datasets_json', 'joins_json',
            'dimensions_json', 'measures_json',
            'time_semantics_json', 'allowed_filters_json', 'parameters_json',
            'is_active', 'is_latest',
            'created_by', 'created_by_name', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'version', 'is_latest', 'created_at', 'updated_at']
    
    def get_created_by_name(self, obj) -> str | None:
        if obj.created_by:
            return obj.created_by.get_full_name() or obj.created_by.email
        return None


class AnalysisModelCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating/updating Analysis Models."""
    
    class Meta:
        model = AnalysisModel
        fields = [
            'name', 'description',
            'datasets_json', 'joins_json',
            'dimensions_json', 'measures_json',
            'time_semantics_json', 'allowed_filters_json', 'parameters_json',
            'is_active'
        ]
    
    def validate_datasets_json(self, value):
        """Validate datasets_json format."""
        if not isinstance(value, list):
            raise serializers.ValidationError("datasets_json must be a list")
        
        if not value:
            raise serializers.ValidationError("At least one dataset is required")
        
        for i, ds in enumerate(value):
            if not isinstance(ds, dict):
                raise serializers.ValidationError(f"Dataset at index {i} must be an object")
            if 'ref' not in ds:
                raise serializers.ValidationError(f"Dataset at index {i} must have 'ref'")
            if 'alias' not in ds:
                raise serializers.ValidationError(f"Dataset at index {i} must have 'alias'")
        
        # Check for duplicate aliases
        aliases = [ds['alias'] for ds in value]
        if len(aliases) != len(set(aliases)):
            raise serializers.ValidationError("Dataset aliases must be unique")
        
        return value
    
    def validate_dimensions_json(self, value):
        """Validate dimensions_json format."""
        if not isinstance(value, list):
            raise serializers.ValidationError("dimensions_json must be a list")
        
        names = []
        for i, dim in enumerate(value):
            if not isinstance(dim, dict):
                raise serializers.ValidationError(f"Dimension at index {i} must be an object")
            if 'name' not in dim:
                raise serializers.ValidationError(f"Dimension at index {i} must have 'name'")
            if 'source' not in dim:
                raise serializers.ValidationError(f"Dimension at index {i} must have 'source'")
            names.append(dim['name'])
        
        if len(names) != len(set(names)):
            raise serializers.ValidationError("Dimension names must be unique")
        
        return value
    
    def validate_measures_json(self, value):
        """Validate measures_json format."""
        if not isinstance(value, list):
            raise serializers.ValidationError("measures_json must be a list")
        
        names = []
        for i, measure in enumerate(value):
            if not isinstance(measure, dict):
                raise serializers.ValidationError(f"Measure at index {i} must be an object")
            if 'name' not in measure:
                raise serializers.ValidationError(f"Measure at index {i} must have 'name'")
            if 'expr' not in measure:
                raise serializers.ValidationError(f"Measure at index {i} must have 'expr'")
            names.append(measure['name'])
        
        if len(names) != len(set(names)):
            raise serializers.ValidationError("Measure names must be unique")
        
        return value
    
    def validate_joins_json(self, value):
        """Validate joins_json format."""
        if value is None:
            return []
        
        if not isinstance(value, list):
            raise serializers.ValidationError("joins_json must be a list")
        
        for i, join in enumerate(value):
            if not isinstance(join, dict):
                raise serializers.ValidationError(f"Join at index {i} must be an object")
            if 'left' not in join:
                raise serializers.ValidationError(f"Join at index {i} must have 'left'")
            if 'right' not in join:
                raise serializers.ValidationError(f"Join at index {i} must have 'right'")
            
            for side in ['left', 'right']:
                side_def = join[side]
                if not isinstance(side_def, dict):
                    raise serializers.ValidationError(f"Join at index {i}: '{side}' must be an object")
                if 'dataset' not in side_def:
                    raise serializers.ValidationError(f"Join at index {i}: '{side}' must have 'dataset'")
                if 'field' not in side_def:
                    raise serializers.ValidationError(f"Join at index {i}: '{side}' must have 'field'")
        
        return value
    
    def validate_allowed_filters_json(self, value):
        """Validate allowed_filters_json format."""
        if value is None:
            return []
        
        if not isinstance(value, list):
            raise serializers.ValidationError("allowed_filters_json must be a list")
        
        for i, f in enumerate(value):
            if not isinstance(f, str):
                raise serializers.ValidationError(f"Filter at index {i} must be a string")
        
        return value
    
    def validate(self, attrs):
        """Cross-field validation."""
        datasets = attrs.get('datasets_json', [])
        joins = attrs.get('joins_json', [])
        dimensions = attrs.get('dimensions_json', [])
        allowed_filters = attrs.get('allowed_filters_json', [])
        
        dataset_aliases = {ds['alias'] for ds in datasets}
        dimension_names = {dim['name'] for dim in dimensions}
        
        # Validate joins reference valid datasets
        for join in joins:
            for side in ['left', 'right']:
                alias = join[side]['dataset']
                if alias not in dataset_aliases:
                    raise serializers.ValidationError({
                        'joins_json': f"Join references unknown dataset alias '{alias}'"
                    })
        
        # Validate allowed_filters reference valid dimensions
        for f in allowed_filters:
            if f not in dimension_names:
                raise serializers.ValidationError({
                    'allowed_filters_json': f"Filter '{f}' is not a declared dimension"
                })
        
        # Validate dimension sources reference valid datasets
        for dim in dimensions:
            source = dim['source']
            if '.' in source:
                alias = source.split('.')[0]
                if alias not in dataset_aliases:
                    raise serializers.ValidationError({
                        'dimensions_json': f"Dimension '{dim['name']}' references unknown dataset '{alias}'"
                    })
        
        return attrs


class AnalyzerRunSerializer(serializers.ModelSerializer):
    """Serializer for AnalyzerRun records."""
    
    analysis_model_name = serializers.CharField(
        source='analysis_model.name',
        read_only=True
    )
    resultset_row_count = serializers.SerializerMethodField()
    duration_seconds = serializers.FloatField(read_only=True)
    
    class Meta:
        model = AnalyzerRun
        fields = [
            'id', 'analysis_model', 'analysis_model_name', 'analysis_model_version',
            'request_json', 'status',
            'resultset', 'resultset_row_count',
            'error_message', 'resolved_datasets_json',
            'execution_time_ms', 'duration_seconds',
            'cache_hit', 'created_by', 'created_at'
        ]
    
    def get_resultset_row_count(self, obj) -> int | None:
        if obj.resultset:
            return obj.resultset.row_count
        return None


class FilterSerializer(serializers.Serializer):
    """Serializer for filter objects in analyze requests."""
    field = serializers.CharField()
    op = serializers.ChoiceField(
        choices=[
            'eq', 'ne', 'gt', 'gte', 'lt', 'lte',
            'in', 'not_in', 'is_null', 'is_not_null',
            'contains', 'starts_with', 'ends_with', 'between'
        ],
        default='eq'
    )
    value = serializers.JSONField(required=False, allow_null=True)
    values = serializers.ListField(
        child=serializers.JSONField(),
        required=False,
        default=list
    )


class OrderBySerializer(serializers.Serializer):
    """Serializer for order_by objects."""
    field = serializers.CharField()
    direction = serializers.ChoiceField(
        choices=['asc', 'desc'],
        default='asc'
    )


class HavingSerializer(serializers.Serializer):
    """
    Serializer for HAVING clauses (post-aggregation filtering).
    
    Phase 2: Allows filtering on measure values after aggregation.
    """
    measure = serializers.CharField(
        help_text="Name of the measure to filter on"
    )
    op = serializers.ChoiceField(
        choices=[
            'eq', 'ne', 'gt', 'gte', 'lt', 'lte',
            'in', 'not_in', 'between'
        ],
        default='eq',
        help_text="Comparison operator"
    )
    value = serializers.JSONField(
        required=False,
        allow_null=True,
        help_text="Value to compare against (for single-value ops)"
    )
    values = serializers.ListField(
        child=serializers.JSONField(),
        required=False,
        default=list,
        help_text="Values for 'in', 'not_in', 'between' operations"
    )


class AnalyzeRequestSerializer(serializers.Serializer):
    """
    Serializer for Analyzer execution requests.
    
    This is the declarative request format that frontends build.
    
    Phase 2 additions:
    - having: Post-aggregation filtering on measures
    """
    analysis_model_id = serializers.UUIDField()
    parameters = serializers.DictField(
        child=serializers.JSONField(),
        required=False,
        default=dict,
        help_text="Parameter values for the analysis"
    )
    dimensions = serializers.ListField(
        child=serializers.CharField(),
        required=False,
        default=list,
        help_text="Dimensions to group by"
    )
    measures = serializers.ListField(
        child=serializers.CharField(),
        required=False,
        default=list,
        help_text="Measures to compute"
    )
    filters = FilterSerializer(
        many=True,
        required=False,
        default=list,
        help_text="Pre-aggregation filters (WHERE clause equivalent)"
    )
    having = HavingSerializer(
        many=True,
        required=False,
        default=list,
        help_text="Post-aggregation filters on measures (HAVING clause equivalent)"
    )
    time_grain = serializers.ChoiceField(
        choices=['hour', 'day', 'week', 'month', 'quarter', 'year'],
        required=False,
        allow_null=True,
        help_text="Time granularity for time-based dimensions"
    )
    order_by = OrderBySerializer(
        many=True,
        required=False,
        default=list,
        help_text="Ordering specification"
    )
    limit = serializers.IntegerField(
        min_value=1,
        max_value=100000,
        required=False,
        allow_null=True,
        help_text="Maximum number of rows to return"
    )
    use_cache = serializers.BooleanField(
        default=True,
        help_text="Whether to use cached results if available"
    )
    
    def validate(self, attrs):
        """Validate that at least dimensions or measures are provided."""
        dimensions = attrs.get('dimensions', [])
        measures = attrs.get('measures', [])
        
        if not dimensions and not measures:
            raise serializers.ValidationError(
                "At least one dimension or measure must be specified"
            )
        
        return attrs
    
    def validate_having(self, value):
        """Validate HAVING clauses require measures to be aggregated."""
        # This is a soft validation - detailed validation happens in Analyzer
        return value


class AnalysisModelValidateSerializer(serializers.Serializer):
    """Serializer for validation-only requests."""
    name = serializers.CharField()
    description = serializers.CharField(required=False, allow_blank=True)
    datasets_json = serializers.JSONField()
    joins_json = serializers.JSONField(required=False, default=list)
    dimensions_json = serializers.JSONField()
    measures_json = serializers.JSONField()
    time_semantics_json = serializers.JSONField(required=False, default=dict)
    allowed_filters_json = serializers.JSONField(required=False, default=list)
    parameters_json = serializers.JSONField(required=False, default=list)
