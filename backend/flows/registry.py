"""UI helpers that expose the shared Flow node registry to the builder."""

from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional

from .core.registry import NodeDefinition, PortSpec, registry

# Historically the builder imported ``REGISTRY`` and ``NodeSpec`` from this
# module. Re-exporting the new runtime-backed objects keeps that surface intact
# while allowing the UI to interact with the canonical NodeDefinition instances.
REGISTRY = registry
NodeSpec = NodeDefinition


def list_definitions() -> Iterable[NodeDefinition]:
    """Return all registered node definitions."""

    return REGISTRY.all()


def _normalise_stage(stage: Optional[str]) -> Optional[str]:
    if not stage:
        return None
    if isinstance(stage, str):
        normalised = stage.strip().lower()
        return normalised or None
    return None


def palette_by_category(stage: Optional[str] = None) -> Dict[str, List[NodeDefinition]]:
    """Group node definitions by category for palette rendering."""

    active_stage = _normalise_stage(stage)
    buckets = REGISTRY.by_category()
    filtered: Dict[str, List[NodeDefinition]] = {}
    for category, definitions in buckets.items():
        visible = [
            definition
            for definition in definitions
            if definition.enabled and definition.is_available_in(active_stage)
        ]
        if not visible:
            continue
        visible.sort(key=lambda d: d.title)
        filtered[category] = visible
    return filtered


def serialize_definitions(stage: Optional[str] = None) -> Dict[str, Dict[str, Any]]:
    """Return a JSON-serialisable representation of the node catalog."""

    active_stage = _normalise_stage(stage)
    data: Dict[str, Dict[str, Any]] = {}
    for definition in REGISTRY.all():
        ports = definition.serialize_ports(definition.default_config)
        stage_flags = definition.stage_flags()
        data[definition.kind] = {
            "kind": definition.kind,
            "title": definition.title,
            "icon": definition.icon,
            "category": definition.category,
            "description": definition.description,
            "enabled": bool(getattr(definition, "enabled", True)),
            "default_config": definition.default_config,
            "form_component": definition.form_component,
            "ports": ports,
            "stages": stage_flags,
            "availability": stage_flags,
            "stage_limited": definition.is_stage_limited(),
            "is_available": definition.is_available_in(active_stage),
            "is_visible": bool(getattr(definition, "enabled", True))
            and definition.is_available_in(active_stage),
            "hints": definition.hints,
        }
    return data


__all__ = [
    "NodeDefinition",
    "NodeSpec",
    "PortSpec",
    "REGISTRY",
    "list_definitions",
    "palette_by_category",
    "serialize_definitions",
]

