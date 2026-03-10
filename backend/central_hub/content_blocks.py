"""Content blocks removed. Kept for backward compatibility - returns empty."""

from __future__ import annotations


def get_visible_blocks_queryset(group: str):
    return []


def render_blocks(group: str) -> str:
    return ""
