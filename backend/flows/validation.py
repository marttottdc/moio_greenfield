import json
from typing import List, Optional, Dict
from pydantic import BaseModel, field_validator
from .registry import REGISTRY, NodeSpec
from .core.formulas import FlowFormulaError, build_formula_scope, validate_formula_expression


class Node(BaseModel):
    id: str
    kind: str
    name: Optional[str] = None
    x: int = 0
    y: int = 0
    config: dict = {}
    ports: Optional[dict] = None
    icon: Optional[str] = None  # agregado para render server-side

    @field_validator("kind")
    @classmethod
    def validate_kind(cls, v):
        if v not in REGISTRY:
            raise ValueError(f"Unknown kind: {v}")
        return v


class Edge(BaseModel):
    id: str
    source: str
    source_port: str
    target: str
    target_port: str


class Graph(BaseModel):
    nodes: List[Node] = []
    edges: List[Edge] = []


def _has_port(node: Node, side: str, name: str) -> bool:
    ports = (node.ports or {}).get(side) or []
    for p in ports:
        # p puede ser PortSpec (objeto) o dict convertido
        if getattr(p, "name", None) == name or (isinstance(p, dict) and p.get("name") == name):
            return True
    return False


def normalize_graph(g: Dict) -> Graph:
    graph = Graph(**g)
    node_map = {n.id: n for n in graph.nodes}

    # Build the allowed function set once for formula validation.
    _allowed_functions = {
        name for name, value in build_formula_scope(context={}).items() if callable(value)
    }

    def _validate_formulas(obj, *, node_id: str, path: str) -> None:
        if isinstance(obj, str):
            raw = obj.strip()
            if raw.startswith("=="):
                return
            if raw.startswith("="):
                expr = raw[1:].strip()
                try:
                    validate_formula_expression(expr, allowed_functions=_allowed_functions)
                except FlowFormulaError as exc:
                    raise ValueError(f"{node_id}: invalid formula at {path}: {exc}") from exc
            return
        if isinstance(obj, dict):
            for k, v in obj.items():
                child_path = f"{path}.{k}" if path else str(k)
                _validate_formulas(v, node_id=node_id, path=child_path)
            return
        if isinstance(obj, list):
            for i, v in enumerate(obj):
                child_path = f"{path}[{i}]"
                _validate_formulas(v, node_id=node_id, path=child_path)
            return

    # enriquecer nodos desde REGISTRY
    for n in graph.nodes:
        spec: NodeSpec = REGISTRY[n.kind]
        # defaults
        if not n.name:
            n.name = spec.title
        if not n.config:
            n.config = spec.default_config.copy()
        # icono & ports calculados
        n.icon = spec.icon
        n.ports = spec.serialize_ports(n.config)
        # validate any '=...' formulas inside node config
        _validate_formulas(n.config, node_id=n.id, path="config")

    # validar edges
    for e in graph.edges:
        src = node_map.get(e.source)
        dst = node_map.get(e.target)
        if not src or not dst:
            raise ValueError(f"Edge {e.id}: missing endpoint")
        if not _has_port(src, "out", e.source_port):
            raise ValueError(f"Edge {e.id}: source port not found ({src.kind}.{e.source_port})")
        if not _has_port(dst, "in", e.target_port):
            raise ValueError(f"Edge {e.id}: target port not found ({dst.kind}.{e.target_port})")

    return graph