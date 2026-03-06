from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Mapping, Optional


JsonSchema = Dict[str, Any]


@dataclass(frozen=True)
class OperationContract:
    """Contract for a single CRUD-like operation on a resource."""

    op: str
    label: str
    description: str
    input_schema: JsonSchema
    output_schema: JsonSchema
    ui_hints: Dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> Dict[str, Any]:
        return {
            "op": self.op,
            "label": self.label,
            "description": self.description,
            "input_schema": self.input_schema,
            "output_schema": self.output_schema,
            "ui_hints": self.ui_hints,
        }


@dataclass(frozen=True)
class ResourceContract:
    slug: str
    label: str
    description: str
    operations: Dict[str, OperationContract]

    def as_summary(self) -> Dict[str, Any]:
        return {
            "slug": self.slug,
            "label": self.label,
            "description": self.description,
            "enabled_operations": sorted(list(self.operations.keys())),
        }

    def as_detail(self) -> Dict[str, Any]:
        return {
            "slug": self.slug,
            "label": self.label,
            "description": self.description,
            "operations": {k: v.as_dict() for k, v in self.operations.items()},
        }


def output_schema_object_with_id(*, object_title: str) -> JsonSchema:
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "success": {"type": "boolean"},
            "id": {"type": "string"},
            "object": {"type": "object", "description": object_title},
        },
        "required": ["success", "id", "object"],
    }


def output_schema_delete() -> JsonSchema:
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "success": {"type": "boolean"},
            "id": {"type": "string"},
        },
        "required": ["success", "id"],
    }


def output_schema_list(*, item_title: str) -> JsonSchema:
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "success": {"type": "boolean"},
            "items": {"type": "array", "items": {"type": "object", "description": item_title}},
            "total": {"type": "integer"},
            "next_cursor": {"type": "string"},
        },
        "required": ["success", "items"],
    }


def schema_id_field(name: str = "id") -> JsonSchema:
    return {"type": "string", "title": name}


def schema_pagination() -> JsonSchema:
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "limit": {"type": "integer", "minimum": 1, "maximum": 500, "default": 50},
            "offset": {"type": "integer", "minimum": 0, "default": 0},
            "cursor": {"type": "string"},
        },
    }


def schema_filter_object(*, properties: Mapping[str, JsonSchema]) -> JsonSchema:
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": dict(properties),
    }

