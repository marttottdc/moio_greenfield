"""
Analytics models for Moio Data Lab.

Defines:
- AnalysisModel: Declarative definition of analytical intent
- AnalyzerRun: Execution record for audit and debugging
"""

from __future__ import annotations

import uuid
from typing import Any

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models

from central_hub.models import Tenant, TenantScopedModel


class AnalysisModel(TenantScopedModel):
    """
    Declarative definition of analytical intent.
    
    An Analysis Model specifies:
    - Which Datasets participate
    - Which analytical joins connect them
    - Which dimensions are exposed
    - Which measures are available
    - How time is interpreted
    - Which filters and parameters are allowed
    
    Analysis Models contain NO execution logic.
    They are interpreted by the Analyzer.
    """
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(
        Tenant,
        on_delete=models.CASCADE,
        related_name='datalab_analysis_models'
    )
    
    # Identity
    name = models.CharField(
        max_length=200,
        help_text="Human-readable name for the analysis model"
    )
    description = models.TextField(
        blank=True,
        help_text="Description of what this analysis model measures"
    )
    version = models.PositiveIntegerField(
        default=1,
        validators=[MinValueValidator(1)],
        help_text="Version number (increments on update)"
    )
    
    # Participating Datasets
    datasets_json = models.JSONField(
        help_text="""
        List of datasets participating in this analysis.
        Format: [{"ref": "dataset-uuid", "alias": "orders"}, ...]
        Each dataset appears as one logical DataFrame to the model.
        """
    )
    
    # Analytical Joins (NOT hydration joins)
    joins_json = models.JSONField(
        default=list,
        blank=True,
        help_text="""
        Analytical joins between datasets.
        Format: [{
            "type": "inner|left|right|full",
            "left": {"dataset": "alias", "field": "column"},
            "right": {"dataset": "alias", "field": "column"},
            "cardinality": "one_to_one|one_to_many|many_to_one|many_to_many"
        }, ...]
        These are ANALYTICAL joins, not internal hydration joins.
        """
    )
    
    # Dimensions (groupable fields)
    dimensions_json = models.JSONField(
        help_text="""
        Exposed dimensions for grouping and filtering.
        Format: [{
            "name": "order_date",
            "source": "orders.created_at",
            "type": "date|datetime|string|integer|boolean",
            "time_grain": ["day", "week", "month", "quarter", "year"] | null,
            "label": "Order Date",
            "description": "When the order was placed"
        }, ...]
        """
    )
    
    # Measures (aggregatable expressions)
    measures_json = models.JSONField(
        help_text="""
        Exposed measures for aggregation.
        Format: [{
            "name": "total_revenue",
            "expr": "SUM(orders.amount)",
            "type": "integer|decimal",
            "format": "number|currency|percent",
            "label": "Total Revenue",
            "description": "Sum of order amounts"
        }, ...]
        """
    )
    
    # Time Semantics
    time_semantics_json = models.JSONField(
        default=dict,
        blank=True,
        help_text="""
        Time interpretation rules.
        Format: {
            "primary_time_field": "order_date",
            "default_grain": "day",
            "default_range": "last_30_days|last_7_days|this_month|this_quarter|this_year",
            "fiscal_year_start": null | "MM-DD",
            "timezone": "UTC" | "tenant"
        }
        """
    )
    
    # Governance
    allowed_filters_json = models.JSONField(
        default=list,
        help_text="""
        Dimension names that can be filtered on.
        Format: ["customer_segment", "product_category", "order_date"]
        Filters on unlisted dimensions are rejected.
        """
    )
    
    # Parameters (required inputs)
    parameters_json = models.JSONField(
        default=list,
        blank=True,
        help_text="""
        Parameters that must be supplied at execution time.
        Format: [{
            "name": "date_from",
            "type": "date|datetime|string|integer|string[]",
            "required": true,
            "default": null | "relative:-30d",
            "label": "Start Date",
            "description": "Analysis start date"
        }, ...]
        """
    )
    
    # Lifecycle
    is_active = models.BooleanField(
        default=True,
        help_text="Whether this model version is active"
    )
    is_latest = models.BooleanField(
        default=True,
        help_text="Whether this is the latest version of this model name"
    )
    
    # Audit
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='created_analysis_models'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        app_label = 'datalab'
        db_table = 'datalab_analysis_model'
        verbose_name = 'Analysis Model'
        verbose_name_plural = 'Analysis Models'
        unique_together = ('tenant', 'name', 'version')
        ordering = ['-updated_at']
        indexes = [
            models.Index(fields=['tenant', 'name', '-version']),
            models.Index(fields=['tenant', 'is_active', 'is_latest']),
        ]
    
    def __str__(self) -> str:
        return f"{self.name} v{self.version}"
    
    def save(self, *args, **kwargs):
        # When saving as latest, mark other versions as not latest
        if self.is_latest:
            AnalysisModel.objects.filter(
                tenant=self.tenant,
                name=self.name,
                is_latest=True
            ).exclude(pk=self.pk).update(is_latest=False)
        super().save(*args, **kwargs)
    
    # ─────────────────────────────────────────────────────────────
    # Validation helpers
    # ─────────────────────────────────────────────────────────────
    
    def get_dimension_names(self) -> set[str]:
        """Return set of declared dimension names."""
        return {d['name'] for d in self.dimensions_json}
    
    def get_measure_names(self) -> set[str]:
        """Return set of declared measure names."""
        return {m['name'] for m in self.measures_json}
    
    def get_allowed_filters(self) -> set[str]:
        """Return set of filterable dimension names."""
        return set(self.allowed_filters_json)
    
    def get_dataset_aliases(self) -> set[str]:
        """Return set of dataset aliases."""
        return {d['alias'] for d in self.datasets_json}
    
    def get_dataset_by_alias(self, alias: str) -> dict[str, Any] | None:
        """Get dataset definition by alias."""
        for ds in self.datasets_json:
            if ds['alias'] == alias:
                return ds
        return None
    
    def get_dimension_by_name(self, name: str) -> dict[str, Any] | None:
        """Get dimension definition by name."""
        for dim in self.dimensions_json:
            if dim['name'] == name:
                return dim
        return None
    
    def get_measure_by_name(self, name: str) -> dict[str, Any] | None:
        """Get measure definition by name."""
        for measure in self.measures_json:
            if measure['name'] == name:
                return measure
        return None
    
    def validate_request(self, request: dict[str, Any]) -> list[dict[str, Any]]:
        """
        Validate an analyzer request against this model's constraints.
        
        Returns list of validation errors (empty if valid).
        """
        errors = []
        
        # Validate dimensions
        requested_dims = set(request.get('dimensions', []))
        invalid_dims = requested_dims - self.get_dimension_names()
        if invalid_dims:
            errors.append({
                'field': 'dimensions',
                'error': f"Dimensions not declared in model: {sorted(invalid_dims)}"
            })
        
        # Validate measures
        requested_measures = set(request.get('measures', []))
        invalid_measures = requested_measures - self.get_measure_names()
        if invalid_measures:
            errors.append({
                'field': 'measures',
                'error': f"Measures not declared in model: {sorted(invalid_measures)}"
            })
        
        # Validate filters
        allowed = self.get_allowed_filters()
        for f in request.get('filters', []):
            field = f.get('field')
            if field and field not in allowed:
                errors.append({
                    'field': 'filters',
                    'error': f"Filter on '{field}' is not allowed. Allowed: {sorted(allowed)}"
                })
        
        # Validate required parameters
        provided_params = set(request.get('parameters', {}).keys())
        for param in self.parameters_json:
            if param.get('required') and param['name'] not in provided_params:
                # Check if there's a default
                if param.get('default') is None:
                    errors.append({
                        'field': 'parameters',
                        'error': f"Required parameter '{param['name']}' is missing"
                    })
        
        # Validate time_grain if provided
        time_grain = request.get('time_grain')
        if time_grain:
            valid_grains = {'hour', 'day', 'week', 'month', 'quarter', 'year'}
            if time_grain not in valid_grains:
                errors.append({
                    'field': 'time_grain',
                    'error': f"Invalid time grain '{time_grain}'. Valid: {sorted(valid_grains)}"
                })
        
        return errors


class AnalyzerRun(TenantScopedModel):
    """
    Execution record of an Analysis Model.
    
    Tracks every Analyzer execution for:
    - Audit and compliance
    - Performance monitoring
    - Debugging
    - Cache management
    """
    
    STATUS_PENDING = 'pending'
    STATUS_RUNNING = 'running'
    STATUS_SUCCESS = 'success'
    STATUS_FAILED = 'failed'
    STATUS_CACHED = 'cached'
    
    STATUS_CHOICES = [
        (STATUS_PENDING, 'Pending'),
        (STATUS_RUNNING, 'Running'),
        (STATUS_SUCCESS, 'Success'),
        (STATUS_FAILED, 'Failed'),
        (STATUS_CACHED, 'Cached'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(
        Tenant,
        on_delete=models.CASCADE,
        related_name='datalab_analyzer_runs'
    )
    
    # What was executed
    analysis_model = models.ForeignKey(
        AnalysisModel,
        on_delete=models.CASCADE,
        related_name='runs',
        help_text="The Analysis Model that was executed"
    )
    analysis_model_version = models.PositiveIntegerField(
        help_text="Version of the Analysis Model at execution time (denormalized)"
    )
    
    # Request (the declarative specification from caller)
    request_json = models.JSONField(
        help_text="""
        The declarative execution request.
        Format: {
            "parameters": {...},
            "dimensions": [...],
            "measures": [...],
            "filters": [...],
            "time_grain": "day",
            "order_by": [...],
            "limit": 1000
        }
        """
    )
    
    # Execution
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default=STATUS_PENDING
    )
    
    # Output
    resultset = models.ForeignKey(
        'datalab.ResultSet',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='analyzer_runs',
        help_text="The ResultSet produced by this run"
    )
    
    # Error tracking
    error_message = models.TextField(
        blank=True,
        help_text="Error message if status is 'failed'"
    )
    error_details_json = models.JSONField(
        default=dict,
        blank=True,
        help_text="Detailed error information for debugging"
    )
    
    # Resolution tracking (which dataset versions were used)
    resolved_datasets_json = models.JSONField(
        default=dict,
        blank=True,
        help_text="""
        Dataset versions resolved at execution time.
        Format: {
            "orders": {"dataset_id": "uuid", "version": 3, "row_count": 15420},
            "customers": {"dataset_id": "uuid", "version": 2, "row_count": 2341}
        }
        """
    )
    
    # Performance metrics
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    execution_time_ms = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Execution time in milliseconds"
    )
    
    # Cache info
    cache_key = models.CharField(
        max_length=64,
        blank=True,
        help_text="Cache key for this request (SHA256)"
    )
    cache_hit = models.BooleanField(
        default=False,
        help_text="Whether this was served from cache"
    )
    
    # Audit
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='analyzer_runs'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        app_label = 'datalab'
        db_table = 'datalab_analyzer_run'
        verbose_name = 'Analyzer Run'
        verbose_name_plural = 'Analyzer Runs'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['tenant', 'status']),
            models.Index(fields=['analysis_model', '-created_at']),
            models.Index(fields=['cache_key']),
            models.Index(fields=['tenant', '-created_at']),
        ]
    
    def __str__(self) -> str:
        return f"AnalyzerRun {self.id} - {self.analysis_model.name} ({self.status})"
    
    @property
    def duration_seconds(self) -> float | None:
        """Calculate duration in seconds."""
        if self.started_at and self.completed_at:
            return (self.completed_at - self.started_at).total_seconds()
        return None
