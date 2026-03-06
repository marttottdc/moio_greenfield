"""Internal contract validation for flow control-flow semantics.

This complements `flows.core.contract` (deterministic placeholder contract) by
enforcing the platform's internal contract rules:

- The internal contract lives in `ctx` (runtime context).
- A Normalize node (`logic_normalize`) is the only place where new `ctx` schema is created.
- Control-flow nodes (Branch/Condition/While) may only evaluate sandboxed expressions over `ctx.*`.
"""

from __future__ import annotations

from collections import deque
from typing import Any, Dict, Mapping, Optional, Set

from .expressions import FlowExpressionError, validate_sandboxed_expression
from .schema import FlowGraph


class FlowInternalContractError(ValueError):
    pass


_CONTROL_KINDS = {"logic_branch", "logic_condition", "logic_while"}
_NORMALIZE_KIND = "logic_normalize"


def _reverse_edges(edges: list[dict]) -> Dict[str, list[str]]:
    rev: Dict[str, list[str]] = {}
    for edge in edges or []:
        src = edge.get("source")
        tgt = edge.get("target")
        if not src or not tgt:
            continue
        rev.setdefault(str(tgt), []).append(str(src))
    return rev


def _upstream_nodes(rev_edges: Dict[str, list[str]], node_id: str) -> Set[str]:
    seen: Set[str] = set()
    q: deque[str] = deque(rev_edges.get(node_id, []))
    while q:
        cur = q.popleft()
        if cur in seen:
            continue
        seen.add(cur)
        for parent in rev_edges.get(cur, []):
            if parent not in seen:
                q.append(parent)
    return seen


def compile_ctx_schema(graph_payload: Mapping[str, Any]) -> dict:
    """Compile a JSON Schema representing the internal ctx contract."""
    graph = FlowGraph.model_validate(graph_payload)
    nodes = [n.model_dump(mode="python") for n in graph.nodes]
    normalize_nodes = [n for n in nodes if n.get("kind") == _NORMALIZE_KIND]

    def _leaf_schema(type_name: Any) -> dict:
        t = str(type_name or "string").lower().strip()
        if t in {"string", "str"}:
            return {"type": "string"}
        if t in {"number", "float"}:
            return {"type": "number"}
        if t in {"integer", "int"}:
            return {"type": "integer"}
        if t in {"boolean", "bool"}:
            return {"type": "boolean"}
        if t in {"array", "list"}:
            return {"type": "array", "items": {}}
        if t in {"object", "dict"}:
            return {"type": "object", "additionalProperties": True}
        return {"type": "string"}

    def _ensure_object_schema(obj: dict) -> dict:
        obj.setdefault("type", "object")
        obj.setdefault("properties", {})
        obj.setdefault("additionalProperties", False)
        return obj

    def _set_schema_path(root: dict, parts: list[str], leaf: dict, *, required: bool) -> None:
        current = _ensure_object_schema(root)
        for i, part in enumerate(parts):
            props = current.setdefault("properties", {})
            if not isinstance(props, dict):
                current["properties"] = {}
                props = current["properties"]

            if i == len(parts) - 1:
                props[part] = leaf
                if required:
                    req = current.setdefault("required", [])
                    if isinstance(req, list) and part not in req:
                        req.append(part)
                return

            nxt = props.get(part)
            if not isinstance(nxt, dict):
                nxt = {"type": "object", "properties": {}, "additionalProperties": False}
                props[part] = nxt

            if required:
                req = current.setdefault("required", [])
                if isinstance(req, list) and part not in req:
                    req.append(part)

            current = _ensure_object_schema(nxt)

    schema: dict = {
        "type": "object",
        "description": "Internal contract produced by Normalize nodes.",
        "properties": {},
        # This schema describes the internal contract roots (not the full runtime ctx).
        "additionalProperties": False,
    }

    # Stable, reserved ctx fields that may be used by templates even without Normalize.
    # These are populated at runtime by various executors (e.g., AI Agent input templates).
    schema["properties"]["workflow"] = {
        "type": "object",
        "properties": {
            "input_as_text": {"type": "string"},
            "input": {"type": "string"},
        },
        "additionalProperties": False,
    }
    # CRM last-result namespace (auto-populated by CRM CRUD executor).
    schema["properties"]["crm"] = {
        "type": "object",
        "additionalProperties": True,
    }
    # Read-only alias to last results.
    schema["properties"]["last"] = {
        "type": "object",
        "properties": {
            "crm": {"type": "object", "additionalProperties": True},
        },
        "additionalProperties": True,
    }

    for node in normalize_nodes:
        cfg = node.get("config") or {}
        mappings = cfg.get("mappings") or cfg.get("mapping") or []
        if not isinstance(mappings, list):
            continue
        for entry in mappings:
            if not isinstance(entry, dict):
                continue
            target = str(entry.get("ctx_path") or entry.get("target") or "").strip()
            if not target.startswith("ctx."):
                continue
            rel = [p for p in target.split(".")[1:] if p]
            if not rel:
                continue
            required = bool(entry.get("required", False))
            _set_schema_path(schema, rel, _leaf_schema(entry.get("type")), required=required)

    return schema


def _schema_lookup(schema: dict, parts: list[str]) -> Optional[dict]:
    """Return the leaf schema at parts, or None if not resolvable."""
    if not isinstance(schema, dict):
        return None

    current: dict = schema
    for part in parts:
        if not isinstance(current, dict):
            return None
        props = current.get("properties")
        if isinstance(props, dict) and part in props:
            nxt = props.get(part)
            if not isinstance(nxt, dict):
                return None
            current = nxt
            continue

        additional = current.get("additionalProperties")
        if additional is True:
            current = {}
            continue
        if isinstance(additional, dict):
            current = additional
            continue
        return None
    return current


def validate_flow_internal_contract(graph_payload: Mapping[str, Any]) -> dict:
    """Validate internal contract rules; returns compiled ctx schema on success."""
    graph = FlowGraph.model_validate(graph_payload)
    nodes_by_id: Dict[str, dict] = {
        str(n.id): n.model_dump(mode="python") for n in graph.nodes
    }
    rev = _reverse_edges([e.model_dump(mode="python") for e in graph.edges])

    upstream_cache: Dict[str, Set[str]] = {}

    def upstream_of(node_id: str) -> Set[str]:
        if node_id not in upstream_cache:
            upstream_cache[node_id] = _upstream_nodes(rev, node_id)
        return upstream_cache[node_id]

    ctx_schema = compile_ctx_schema(graph_payload)

    errors: list[str] = []

    def _has_upstream_normalize(node_id: str) -> bool:
        for parent in upstream_of(node_id):
            if (nodes_by_id.get(parent) or {}).get("kind") == _NORMALIZE_KIND:
                return True
        return False

    # 1) Control-flow nodes require Normalize upstream
    for node_id, node in nodes_by_id.items():
        kind = str(node.get("kind") or "")
        if kind not in _CONTROL_KINDS:
            continue
        if not _has_upstream_normalize(node_id):
            errors.append(f"{node_id}: {kind} requires a Normalize node upstream")

    # 2) Normalize nodes must declare mappings if used (best-effort enforcement)
    for node_id, node in nodes_by_id.items():
        if node.get("kind") != _NORMALIZE_KIND:
            continue
        cfg = node.get("config") or {}
        mappings = cfg.get("mappings") or cfg.get("mapping") or []
        if not isinstance(mappings, list) or not mappings:
            # If there is any downstream control-flow from this normalize, require mappings.
            downstream_controls = False
            # naive: scan nodes that have this normalize upstream
            for other_id, other in nodes_by_id.items():
                if str(other.get("kind") or "") in _CONTROL_KINDS and node_id in upstream_of(other_id):
                    downstream_controls = True
                    break
            if downstream_controls:
                errors.append(f"{node_id}: Normalize must define at least one mapping")

    # 3) Expressions must be sandboxed and only reference defined ctx paths
    for node_id, node in nodes_by_id.items():
        kind = str(node.get("kind") or "")
        cfg = node.get("config") or {}
        if kind == "logic_branch":
            rules = (cfg or {}).get("rules") or []
            if isinstance(rules, list):
                for idx, rule in enumerate(rules):
                    if not isinstance(rule, dict):
                        continue
                    expr = rule.get("expr")
                    if expr in (None, ""):
                        continue
                    try:
                        result = validate_sandboxed_expression(str(expr))
                    except FlowExpressionError as exc:
                        errors.append(f"{node_id}: invalid branch expr in rules[{idx}]: {exc}")
                        continue
                    for path in result.referenced_ctx_paths:
                        # path like "ctx.event.foo"
                        parts = [p for p in path.split(".")[1:] if p]
                        if not parts:
                            continue
                        if _schema_lookup(ctx_schema, parts) is None:
                            errors.append(f"{node_id}: expr references undefined ctx path '{path}'")

        if kind == "logic_condition":
            expr = (cfg or {}).get("expr")
            if expr not in (None, ""):
                try:
                    result = validate_sandboxed_expression(str(expr))
                except FlowExpressionError as exc:
                    errors.append(f"{node_id}: invalid condition expr: {exc}")
                else:
                    for path in result.referenced_ctx_paths:
                        parts = [p for p in path.split(".")[1:] if p]
                        if parts and _schema_lookup(ctx_schema, parts) is None:
                            errors.append(f"{node_id}: expr references undefined ctx path '{path}'")

        if kind == "logic_while":
            expr = (cfg or {}).get("expr")
            if expr not in (None, ""):
                try:
                    result = validate_sandboxed_expression(str(expr))
                except FlowExpressionError as exc:
                    errors.append(f"{node_id}: invalid while expr: {exc}")
                else:
                    for path in result.referenced_ctx_paths:
                        parts = [p for p in path.split(".")[1:] if p]
                        if parts and _schema_lookup(ctx_schema, parts) is None:
                            errors.append(f"{node_id}: expr references undefined ctx path '{path}'")

    if errors:
        joined = "\n- " + "\n- ".join(errors)
        raise FlowInternalContractError("Flow internal contract validation failed:" + joined)

    return ctx_schema


__all__ = [
    "FlowInternalContractError",
    "compile_ctx_schema",
    "validate_flow_internal_contract",
]

