"""
Widget runners for Data Lab.

Render widgets by querying DataSources and formatting data appropriately.
"""
from __future__ import annotations

import logging
from typing import Any

import pandas as pd

from datalab.core.models import DataSource
from datalab.core.storage import get_storage
from datalab.panels.models import Widget, WidgetType

logger = logging.getLogger(__name__)


class WidgetRunnerError(Exception):
    """Raised when widget rendering fails."""
    pass


class WidgetRunner:
    """Base class for widget runners."""
    
    def __init__(self):
        self.storage = get_storage()
    
    def render(self, widget: Widget) -> dict[str, Any]:
        """
        Render a widget.
        
        Args:
            widget: Widget to render
            
        Returns:
            Dictionary with rendered widget data
        """
        # Load data from DataSource
        df = self._load_widget_data(widget)
        
        # Apply widget-specific rendering
        return self._render_dataframe(df, widget)
    
    def _load_widget_data(self, widget: Widget) -> pd.DataFrame:
        """Load data from widget's DataSource."""
        try:
            datasource = DataSource.objects.get(id=widget.datasource_id, tenant=widget.tenant)
        except DataSource.DoesNotExist:
            raise WidgetRunnerError(f"DataSource {widget.datasource_id} not found")
        
        # Load based on DataSource type
        if datasource.type == DataSource.DataSourceType.RESULTSET:
            from datalab.core.models import ResultSet as RS
            resultset = RS.objects.get(id=datasource.ref_id, tenant=widget.tenant)
            if resultset.storage == 'parquet':
                return self.storage.load_parquet(resultset.id)
            else:
                return pd.DataFrame(resultset.preview_json)
        
        elif datasource.type == DataSource.DataSourceType.SNAPSHOT:
            from datalab.core.models import Snapshot
            snapshot = Snapshot.objects.get(id=datasource.ref_id, tenant=widget.tenant)
            resultset = snapshot.resultset
            if resultset.storage == 'parquet':
                return self.storage.load_parquet(resultset.id)
            else:
                return pd.DataFrame(resultset.preview_json)
        
        elif datasource.type == DataSource.DataSourceType.CRM:
            from datalab.crm_sources.models import CRMView
            from datalab.crm_sources.orm_builder import CRMQueryORMBuilder
            view = CRMView.objects.get(id=datasource.ref_id, tenant=widget.tenant)
            builder = CRMQueryORMBuilder()
            return builder.build_queryset(view, filters=None)
        
        else:
            raise WidgetRunnerError(f"Unsupported DataSource type: {datasource.type}")
    
    def _render_dataframe(self, df: pd.DataFrame, widget: Widget) -> dict[str, Any]:
        """Render DataFrame for this widget type. Override in subclasses."""
        raise NotImplementedError


class TableWidgetRunner(WidgetRunner):
    """Runner for table widgets."""
    
    def _render_dataframe(self, df: pd.DataFrame, widget: Widget) -> dict[str, Any]:
        """Render DataFrame as table data."""
        config = widget.config_json or {}
        
        # Column selection
        columns = config.get('columns', df.columns.tolist())
        if columns:
            df = df[columns]
        
        # Pagination
        page = config.get('page', 1)
        page_size = config.get('page_size', 50)
        offset = (page - 1) * page_size
        
        # Sorting
        sort_by = config.get('sort_by')
        if sort_by:
            ascending = config.get('sort_ascending', True)
            df = df.sort_values(by=sort_by, ascending=ascending)
        
        # Filtering (basic)
        filters = config.get('filters', {})
        if filters:
            for col, value in filters.items():
                if col in df.columns:
                    if isinstance(value, list):
                        df = df[df[col].isin(value)]
                    else:
                        df = df[df[col] == value]
        
        total_rows = len(df)
        paginated_df = df.iloc[offset:offset + page_size]
        
        return {
            'type': 'table',
            'columns': paginated_df.columns.tolist(),
            'rows': paginated_df.to_dict(orient='records'),
            'pagination': {
                'page': page,
                'page_size': page_size,
                'total_rows': total_rows,
                'total_pages': (total_rows + page_size - 1) // page_size
            }
        }


class KPIWidgetRunner(WidgetRunner):
    """Runner for KPI widgets."""
    
    def _render_dataframe(self, df: pd.DataFrame, widget: Widget) -> dict[str, Any]:
        """Render DataFrame as KPI value."""
        config = widget.config_json or {}
        
        # Column to aggregate
        value_column = config.get('value_column')
        if not value_column or value_column not in df.columns:
            raise WidgetRunnerError(f"KPI widget missing valid 'value_column': {value_column}")
        
        # Aggregation function
        aggregation = config.get('aggregation', 'sum')
        
        if aggregation == 'sum':
            value = float(df[value_column].sum())
        elif aggregation == 'avg' or aggregation == 'mean':
            value = float(df[value_column].mean())
        elif aggregation == 'min':
            value = float(df[value_column].min())
        elif aggregation == 'max':
            value = float(df[value_column].max())
        elif aggregation == 'count':
            value = float(len(df))
        else:
            raise WidgetRunnerError(f"Unknown aggregation: {aggregation}")
        
        # Format
        format_str = config.get('format', '{:,.0f}')
        formatted_value = format_str.format(value)
        
        # Comparison (optional)
        comparison = None
        if config.get('comparison_column'):
            comparison_value = float(df[config['comparison_column']].sum())
            diff = value - comparison_value
            comparison = {
                'value': comparison_value,
                'diff': diff,
                'percent_change': (diff / comparison_value * 100) if comparison_value != 0 else 0
            }
        
        return {
            'type': 'kpi',
            'value': value,
            'formatted_value': formatted_value,
            'aggregation': aggregation,
            'comparison': comparison,
            'label': config.get('label', '')
        }


class ChartWidgetRunner(WidgetRunner):
    """Base runner for chart widgets."""
    
    def _render_dataframe(self, df: pd.DataFrame, widget: Widget) -> dict[str, Any]:
        """Render DataFrame as chart data."""
        config = widget.config_json or {}
        
        # X and Y axes
        x_column = config.get('x_column')
        y_column = config.get('y_column')
        
        if not x_column or not y_column:
            raise WidgetRunnerError(f"Chart widget missing 'x_column' or 'y_column'")
        
        if x_column not in df.columns or y_column not in df.columns:
            raise WidgetRunnerError(f"Chart columns not found in data")
        
        # Group by X column and aggregate Y column
        aggregation = config.get('aggregation', 'sum')
        
        if aggregation == 'sum':
            grouped = df.groupby(x_column)[y_column].sum()
        elif aggregation == 'avg' or aggregation == 'mean':
            grouped = df.groupby(x_column)[y_column].mean()
        elif aggregation == 'count':
            grouped = df.groupby(x_column)[y_column].count()
        else:
            grouped = df.groupby(x_column)[y_column].sum()
        
        # Limit number of data points
        limit = config.get('limit', 100)
        if len(grouped) > limit:
            grouped = grouped.nlargest(limit)
        
        # Format for chart
        chart_data = {
            'labels': grouped.index.tolist(),
            'values': grouped.values.tolist(),
        }
        
        return {
            'type': self._get_chart_type(),
            'data': chart_data,
            'x_label': config.get('x_label', x_column),
            'y_label': config.get('y_label', y_column),
        }
    
    def _get_chart_type(self) -> str:
        """Return chart type. Override in subclasses."""
        raise NotImplementedError


class LineChartWidgetRunner(ChartWidgetRunner):
    """Runner for line chart widgets."""
    
    def _get_chart_type(self) -> str:
        return 'linechart'


class BarChartWidgetRunner(ChartWidgetRunner):
    """Runner for bar chart widgets."""
    
    def _get_chart_type(self) -> str:
        return 'barchart'


class PieChartWidgetRunner(ChartWidgetRunner):
    """Runner for pie chart widgets."""
    
    def _get_chart_type(self) -> str:
        return 'piechart'


# Registry of widget runners
WIDGET_RUNNERS = {
    WidgetType.TABLE: TableWidgetRunner,
    WidgetType.KPI: KPIWidgetRunner,
    WidgetType.LINECHART: LineChartWidgetRunner,
    WidgetType.BARCHART: BarChartWidgetRunner,
    WidgetType.PIECHART: PieChartWidgetRunner,
}


def get_widget_runner(widget_type: str) -> WidgetRunner:
    """Get widget runner for a widget type."""
    runner_class = WIDGET_RUNNERS.get(widget_type)
    if not runner_class:
        raise WidgetRunnerError(f"No runner available for widget type: {widget_type}")
    return runner_class()
