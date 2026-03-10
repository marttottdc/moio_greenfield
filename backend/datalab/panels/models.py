"""
Panel and Widget models for Data Lab.

Panels are bound to Analysis Models and contain Widgets for visualization.
"""
from __future__ import annotations

import uuid
from typing import Any

from django.conf import settings
from django.db import models

from central_hub.models import Tenant, TenantScopedModel


class Panel(TenantScopedModel):
    """
    A dashboard panel bound to exactly one Analysis Model.
    
    Panels are presentation containers. They:
    - Define layout and grid positioning
    - Contain widgets
    - Pass parameters to the Analyzer
    - Display ResultSets
    
    Panels do NOT:
    - Define analytics
    - Own business logic
    - Add joins or filters beyond the Analysis Model
    """
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name='datalab_panels')
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    
    # ─────────────────────────────────────────────────────────────
    # Analysis Model binding (v4)
    # ─────────────────────────────────────────────────────────────
    analysis_model = models.ForeignKey(
        'datalab.AnalysisModel',
        on_delete=models.PROTECT,  # Prevent deletion of used models
        related_name='panels',
        null=True,  # Nullable for migration, should be required in new panels
        blank=True,
        help_text="The Analysis Model this panel is bound to. All widgets inherit this binding."
    )
    
    # Default parameters for this panel
    default_parameters_json = models.JSONField(
        default=dict,
        blank=True,
        help_text="""
        Default parameter values for this panel.
        Format: {
            "date_from": "relative:-30d",
            "date_to": "relative:today",
            "segments": ["enterprise"]
        }
        Supports relative date syntax: relative:-Nd, relative:today, relative:start_of_month
        """
    )
    
    # Layout configuration (JSON)
    layout_json = models.JSONField(
        default=dict,
        blank=True,
        help_text="Panel layout configuration (grid, positioning, etc.)"
    )
    
    # Sharing configuration
    is_public = models.BooleanField(default=False, help_text="If True, panel is visible to all users")
    shared_with_roles = models.JSONField(
        default=list,
        blank=True,
        help_text="List of role names that can access this panel"
    )
    
    # Refresh settings
    auto_refresh_seconds = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Auto-refresh interval in seconds (null = no auto-refresh)"
    )
    
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='created_datalab_panels'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'datalab_panel'
        verbose_name = 'Panel'
        verbose_name_plural = 'Panels'
        ordering = ['-updated_at']
        indexes = [
            models.Index(fields=['tenant', 'is_public']),
            models.Index(fields=['tenant', 'name']),
            models.Index(fields=['analysis_model']),
        ]
    
    def __str__(self) -> str:
        if self.analysis_model:
            return f"{self.name} ({self.analysis_model.name})"
        return self.name


class WidgetType(models.TextChoices):
    """Types of widgets available in Data Lab."""
    TABLE = 'table', 'Table'
    KPI = 'kpi', 'KPI'
    KPI_COMPARISON = 'kpi_comparison', 'KPI with Comparison'
    LINECHART = 'linechart', 'Line Chart'
    AREACHART = 'areachart', 'Area Chart'
    BARCHART = 'barchart', 'Bar Chart'
    BARCHART_HORIZONTAL = 'barchart_h', 'Horizontal Bar Chart'
    PIECHART = 'piechart', 'Pie Chart'
    DONUTCHART = 'donutchart', 'Donut Chart'
    SCATTER = 'scatter', 'Scatter Plot'
    HEATMAP = 'heatmap', 'Heatmap'
    GAUGE = 'gauge', 'Gauge'
    SPARKLINE = 'sparkline', 'Sparkline'
    TEXT = 'text', 'Text/Markdown'


class Widget(TenantScopedModel):
    """
    A visualization component within a Panel.
    
    Widgets are PURE visualization components. They:
    - Map ResultSet fields to visual elements
    - Control formatting and interactivity
    - Reference dimensions/measures from the parent Panel's Analysis Model
    
    Widgets CANNOT:
    - Add joins
    - Add filters outside the model
    - Redefine metrics
    - Execute computations
    """
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name='datalab_widgets')
    panel = models.ForeignKey(
        Panel,
        on_delete=models.CASCADE,
        related_name='widgets',
        related_query_name='widget'
    )
    
    name = models.CharField(max_length=200)
    widget_type = models.CharField(max_length=20, choices=WidgetType.choices)
    
    # ─────────────────────────────────────────────────────────────
    # Legacy data binding (deprecated in v4, kept for migration)
    # ─────────────────────────────────────────────────────────────
    datasource_id = models.UUIDField(
        null=True,
        blank=True,
        help_text="DEPRECATED: Use field_mappings_json instead. Widgets now inherit Analysis Model from Panel."
    )
    
    # ─────────────────────────────────────────────────────────────
    # v4: Field mappings (references to Analysis Model dimensions/measures)
    # ─────────────────────────────────────────────────────────────
    field_mappings_json = models.JSONField(
        default=dict,
        blank=True,
        help_text="""
        Maps widget visual elements to Analysis Model fields.
        
        Format varies by widget type:
        
        KPI:
        {
            "measure": "total_revenue",
            "comparison_measure": "previous_total_revenue",
            "format": "currency"
        }
        
        Line/Bar/Area Chart:
        {
            "x_axis": "order_date",
            "y_axis": ["total_revenue", "order_count"],
            "series_by": "customer_segment",
            "stack": false
        }
        
        Pie/Donut Chart:
        {
            "category": "customer_segment",
            "value": "total_revenue"
        }
        
        Table:
        {
            "columns": [
                {"field": "order_date", "label": "Date", "format": "date"},
                {"field": "total_revenue", "label": "Revenue", "format": "currency"}
            ],
            "sortable": true,
            "paginated": true
        }
        """
    )
    
    # Widget-specific display configuration
    display_config_json = models.JSONField(
        default=dict,
        blank=True,
        help_text="""
        Display and formatting options.
        Format: {
            "title": "Revenue by Segment",
            "subtitle": "Last 30 days",
            "show_legend": true,
            "legend_position": "bottom",
            "colors": ["#3b82f6", "#10b981", "#f59e0b"],
            "axis_labels": {"x": "Date", "y": "Amount"},
            "number_format": {"locale": "en-US", "currency": "USD"},
            "empty_state_message": "No data available"
        }
        """
    )
    
    # Optional widget-level filter (must be within allowed_filters)
    widget_filters_json = models.JSONField(
        default=list,
        blank=True,
        help_text="""
        Additional filters applied only to this widget.
        Must reference fields in Analysis Model's allowed_filters.
        Format: [{"field": "customer_segment", "op": "eq", "value": "enterprise"}]
        """
    )
    
    # Legacy config (kept for backward compatibility)
    config_json = models.JSONField(
        default=dict,
        blank=True,
        help_text="DEPRECATED: Use field_mappings_json and display_config_json instead."
    )
    
    # Layout within panel (grid-based)
    position_x = models.IntegerField(default=0, help_text="X position in grid (0-based)")
    position_y = models.IntegerField(default=0, help_text="Y position in grid (0-based)")
    width = models.IntegerField(default=4, help_text="Width in grid units")
    height = models.IntegerField(default=3, help_text="Height in grid units")
    
    is_visible = models.BooleanField(default=True)
    order = models.IntegerField(default=0, help_text="Display order within panel")
    
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='created_datalab_widgets'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'datalab_widget'
        verbose_name = 'Widget'
        verbose_name_plural = 'Widgets'
        ordering = ['panel', 'order', 'position_y', 'position_x']
        indexes = [
            models.Index(fields=['panel', 'order']),
            models.Index(fields=['tenant', 'widget_type']),
        ]
    
    def __str__(self) -> str:
        return f"{self.name} ({self.get_widget_type_display()})"
    
    def validate_field_mappings(self) -> list[dict[str, Any]]:
        """
        Validate that field mappings reference valid Analysis Model fields.
        Returns list of validation errors.
        """
        errors = []
        
        if not self.panel.analysis_model:
            errors.append({
                'field': 'panel',
                'error': 'Panel has no Analysis Model bound'
            })
            return errors
        
        analysis_model = self.panel.analysis_model
        valid_dimensions = analysis_model.get_dimension_names()
        valid_measures = analysis_model.get_measure_names()
        valid_fields = valid_dimensions | valid_measures
        
        # Extract all field references from mappings
        mappings = self.field_mappings_json
        referenced_fields = set()
        
        # Handle different widget type mappings
        for key in ['measure', 'comparison_measure', 'x_axis', 'category', 'value', 'size', 'color']:
            if key in mappings and mappings[key]:
                if isinstance(mappings[key], str):
                    referenced_fields.add(mappings[key])
        
        for key in ['y_axis']:
            if key in mappings:
                if isinstance(mappings[key], list):
                    referenced_fields.update(mappings[key])
                elif isinstance(mappings[key], str):
                    referenced_fields.add(mappings[key])
        
        if 'series_by' in mappings and mappings['series_by']:
            referenced_fields.add(mappings['series_by'])
        
        if 'columns' in mappings:
            for col in mappings['columns']:
                if isinstance(col, dict) and 'field' in col:
                    referenced_fields.add(col['field'])
        
        # Validate
        invalid_fields = referenced_fields - valid_fields
        if invalid_fields:
            errors.append({
                'field': 'field_mappings_json',
                'error': f"Referenced fields not in Analysis Model: {sorted(invalid_fields)}"
            })
        
        return errors