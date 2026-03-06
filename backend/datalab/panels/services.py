"""
Services for Panel rendering and widget execution.
"""
from __future__ import annotations

import logging

from datalab.panels.models import Panel, Widget
from datalab.panels.widget_runners import get_widget_runner, WidgetRunnerError

logger = logging.getLogger(__name__)


class PanelService:
    """Service for rendering panels."""
    
    def render_panel(self, panel: Panel) -> dict:
        """
        Render a panel with all its widgets.
        
        Args:
            panel: Panel to render
            
        Returns:
            Dictionary with panel data and rendered widgets
        """
        widgets = Widget.objects.filter(panel=panel, is_visible=True).order_by('order')
        
        rendered_widgets = []
        for widget in widgets:
            try:
                runner = get_widget_runner(widget.widget_type)
                widget_data = runner.render(widget)
                
                rendered_widgets.append({
                    'id': str(widget.id),
                    'name': widget.name,
                    'type': widget.widget_type,
                    'position': {
                        'x': widget.position_x,
                        'y': widget.position_y,
                        'width': widget.width,
                        'height': widget.height,
                    },
                    'data': widget_data,
                })
            except WidgetRunnerError as e:
                logger.error(f"Failed to render widget {widget.id}: {e}")
                rendered_widgets.append({
                    'id': str(widget.id),
                    'name': widget.name,
                    'type': widget.widget_type,
                    'error': str(e),
                })
        
        return {
            'panel': {
                'id': str(panel.id),
                'name': panel.name,
                'description': panel.description,
            },
            'widgets': rendered_widgets,
            'layout': panel.layout_json,
        }
