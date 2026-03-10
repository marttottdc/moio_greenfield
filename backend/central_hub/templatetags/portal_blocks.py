from django import template

from django.utils.safestring import mark_safe

from central_hub.content_blocks import render_blocks as render_blocks_helper

register = template.Library()


@register.simple_tag
def render_blocks(group: str) -> str:
    """Return the HTML for the requested content block group."""

    return mark_safe(render_blocks_helper(group))
