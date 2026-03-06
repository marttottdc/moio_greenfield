"""Utilities for rendering tenant scoped portal content blocks.

The component templates referenced by ``ComponentTemplate.template_path`` should
live under ``portal/templates/portal/partials/`` so they can be shared across
apps and rendered through Django's template loader.
"""

from __future__ import annotations

from typing import Iterable

from django.template.loader import render_to_string
from django.db.models import Q

from portal.context_utils import current_tenant
from portal.models import ContentBlock


def _render_block(block: ContentBlock) -> str:
    template_path = block.component.template_path
    context = {**(block.context or {})}

    context.setdefault('block', block)
    context.setdefault('component', block.component)
    context.setdefault('title', block.title)

    return render_to_string(template_path, context)


def get_visible_blocks_queryset(group: str):
    tenant = current_tenant.get()

    queryset = ContentBlock.objects.filter(group=group, is_active=True)

    if tenant:
        queryset = queryset.filter(Q(visibility=ContentBlock.Visibility.PUBLIC) | Q(tenant=tenant))
    else:
        queryset = queryset.filter(visibility=ContentBlock.Visibility.PUBLIC)

    return queryset.select_related('component').order_by('order', 'id')


def render_blocks(group: str) -> str:
    """Render the active blocks that belong to ``group`` for the current tenant."""

    queryset = get_visible_blocks_queryset(group)

    rendered: Iterable[str] = (_render_block(block) for block in queryset)
    return ''.join(rendered)
