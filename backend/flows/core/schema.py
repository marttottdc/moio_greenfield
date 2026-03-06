"""Typed schema and validation helpers for flow graphs."""
from __future__ import annotations

from typing import Any, Dict, List, Mapping, Sequence

from pydantic import BaseModel, Field, ValidationError, model_validator


class PortDefinition(BaseModel):
    """Metadata describing a port exposed by a node."""

    name: str = Field(..., min_length=1)
    label: str | None = None
    type: str | None = None
    required: bool = False
    meta: Dict[str, Any] = Field(default_factory=dict)


class Node(BaseModel):
    """Node on the flow canvas."""

    id: str = Field(..., min_length=1)
    kind: str = Field(..., min_length=1)
    name: str | None = None
    x: float = 0.0
    y: float = 0.0
    config: Dict[str, Any] = Field(default_factory=dict)
    ports: Dict[str, List[PortDefinition]] = Field(default_factory=dict)
    meta: Dict[str, Any] = Field(default_factory=dict)


class Edge(BaseModel):
    """Directed edge connecting two nodes."""

    id: str = Field(..., min_length=1)
    source: str = Field(..., min_length=1)
    target: str = Field(..., min_length=1)
    source_port: str | None = None
    target_port: str | None = None
    config: Dict[str, Any] = Field(default_factory=dict)
    meta: Dict[str, Any] = Field(default_factory=dict)


class FlowGraph(BaseModel):
    """Flow graph comprised of nodes and edges."""

    nodes: List[Node] = Field(default_factory=list)
    edges: List[Edge] = Field(default_factory=list)
    meta: Dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _validate_structure(self) -> "FlowGraph":
        node_ids: List[str] = [node.id for node in self.nodes]
        duplicates = _find_duplicates(node_ids)
        if duplicates:
            raise ValueError(
                f"Duplicate node ids detected: {', '.join(sorted(duplicates))}"
            )

        edge_ids: List[str] = [edge.id for edge in self.edges]
        duplicate_edges = _find_duplicates(edge_ids)
        if duplicate_edges:
            raise ValueError(
                f"Duplicate edge ids detected: {', '.join(sorted(duplicate_edges))}"
            )

        node_set = set(node_ids)
        dangling_sources = sorted({edge.source for edge in self.edges} - node_set)
        dangling_targets = sorted({edge.target for edge in self.edges} - node_set)
        if dangling_sources or dangling_targets:
            problems: list[str] = []
            if dangling_sources:
                problems.append(
                    "missing source nodes: " + ", ".join(dangling_sources)
                )
            if dangling_targets:
                problems.append(
                    "missing target nodes: " + ", ".join(dangling_targets)
                )
            raise ValueError("Edges reference unknown nodes (" + "; ".join(problems) + ")")

        return self

    def as_dict(self) -> Dict[str, Any]:
        """Return a JSON-serialisable representation of the graph."""

        return self.model_dump(mode="json")


GraphValidationError = ValidationError


def validate_graph_payload(data: Mapping[str, Any] | FlowGraph) -> FlowGraph:
    """Validate and normalise an incoming graph payload.

    Accepts either a raw mapping (e.g., the JSON body received from the
    composer) or an already instantiated :class:`FlowGraph`.
    """

    if isinstance(data, FlowGraph):
        return data
    if not isinstance(data, Mapping):
        raise TypeError("Graph payload must be a mapping or FlowGraph instance")
    return FlowGraph.model_validate(data)


def _find_duplicates(items: Sequence[str]) -> set[str]:
    seen: set[str] = set()
    duplicates: set[str] = set()
    for item in items:
        if item in seen:
            duplicates.add(item)
        else:
            seen.add(item)
    return duplicates


__all__ = [
    "Edge",
    "FlowGraph",
    "GraphValidationError",
    "Node",
    "PortDefinition",
    "validate_graph_payload",
]
