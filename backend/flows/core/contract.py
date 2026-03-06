"""Strict flow contract validation.

Flow language contract (deterministic):
- input.body.*              (trigger input payload, schema-defined)
- nodes.<nodeId>.output.*   (upstream node outputs, schema-defined)
- config.*                  (flow-scoped immutable constants, schema-defined)
- ctx.*                     (internal contract produced by Normalize, schema-defined)

Only simple dot-paths are allowed inside placeholders: {{ path }}.
"""

from __future__ import annotations

import json
import re
from collections import deque
from typing import Any, Dict, Iterable, Mapping, Optional, Set, Tuple

from jsonschema import Draft202012Validator

from .lib import _parse_contract_path
from .schema import FlowGraph
from .registry import registry as node_registry
from moio_platform.core.events.schemas import get_event_payload_schema

_PLACEHOLDER_RE = re.compile(r"\{\{\s*(.*?)\s*\}\}")
_LIKELY_CONTRACT_PATH_RE = re.compile(
    r"^(input\.body|nodes\.[A-Za-z0-9_-]+\.output|config|ctx)(\.[A-Za-z0-9_-]+)*$"
)


class FlowContractError(ValueError):
    pass


def _iter_string_values(value: Any) -> Iterable[str]:
    """Yield all string leaves from nested dict/list structures."""
    if isinstance(value, str):
        yield value
        return
    if isinstance(value, dict):
        for v in value.values():
            yield from _iter_string_values(v)
        return
    if isinstance(value, list):
        for v in value:
            yield from _iter_string_values(v)


def _assert_no_dynamic_config(config_values: Any) -> list[str]:
    """Reject config values that contain template syntax (must be static constants)."""
    errors: list[str] = []
    for s in _iter_string_values(config_values):
        if "{{" in s or "}}" in s:
            errors.append("config_values must not contain '{{' or '}}' (no dynamic config)")
            break
    return errors

def _find_placeholders(text: str) -> list[str]:
    return [m.group(1) for m in _PLACEHOLDER_RE.finditer(text or "")]


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


def _select_output_schema(node: dict) -> dict:
    kind = node.get("kind") or ""
    config = node.get("config") or {}
    definition = node_registry.get(str(kind))
    if not definition:
        # Unknown node kind: cannot validate schema paths.
        raise FlowContractError(f"Unknown node kind '{kind}' (node_id={node.get('id')})")
    port_map = definition.compute_ports(config if isinstance(config, dict) else {})
    out_ports = (port_map or {}).get("out") or []
    schemas = [p.schema for p in out_ports if getattr(p, "schema", None)]
    if not schemas:
        return {}
    if len(schemas) == 1:
        return schemas[0] or {}
    return {"anyOf": [s for s in schemas if isinstance(s, dict)]}


def _event_payload_schema(event_name: str) -> dict:
    try:
        return get_event_payload_schema(event_name)
    except KeyError as exc:
        raise FlowContractError(str(exc)) from exc


def _webhook_expected_schema(trigger_node: dict) -> dict:
    cfg = trigger_node.get("config") or {}
    raw = (cfg or {}).get("expected_schema")
    if raw is None or raw == "":
        raise FlowContractError("Webhook trigger is missing expected_schema")
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str):
        try:
            parsed = json.loads(raw)
        except Exception as exc:
            raise FlowContractError("Invalid webhook expected_schema (must be valid JSON)") from exc
        if not isinstance(parsed, dict) or not parsed:
            raise FlowContractError("Invalid webhook expected_schema (must be a non-empty JSON object)")
        return parsed
    raise FlowContractError("Invalid webhook expected_schema type")


def _trigger_input_schema(graph: FlowGraph) -> dict:
    trigger_nodes = [n for n in graph.nodes if str(n.kind).startswith("trigger_")]
    if len(trigger_nodes) != 1:
        raise FlowContractError(f"Flow graph must contain exactly one trigger node (found {len(trigger_nodes)})")
    trigger = trigger_nodes[0].model_dump(mode="python")
    kind = str(trigger.get("kind") or "")
    if kind == "trigger_webhook":
        return _webhook_expected_schema(trigger)
    if kind == "trigger_event":
        cfg = trigger.get("config") or {}
        event_name = (cfg or {}).get("event") or (cfg or {}).get("event_name") or (cfg or {}).get("topic")
        if not event_name:
            raise FlowContractError("Event trigger is missing event_name")
        return _event_payload_schema(str(event_name))
    if kind == "trigger_scheduled":
        return {"type": "object", "properties": {}, "additionalProperties": False}
    if kind == "trigger_manual":
        raise FlowContractError("Manual trigger flows cannot be published/armed under strict contract")
    # Other trigger kinds: require explicit schema support before allowing publish.
    raise FlowContractError(f"Unsupported trigger kind '{kind}' under strict contract")


def _schema_lookup(schema: dict, parts: list[str]) -> Optional[dict]:
    """Return the leaf schema at parts, or None if not resolvable."""
    if not isinstance(schema, dict):
        return None

    # Handle unions at root.
    for union_key in ("anyOf", "oneOf", "allOf"):
        if union_key in schema and isinstance(schema[union_key], list):
            options = schema[union_key]
            hits = []
            for opt in options:
                if isinstance(opt, dict):
                    leaf = _schema_lookup(opt, parts)
                    if leaf is not None:
                        hits.append(leaf)
            if not hits:
                return None
            # If multiple possibilities, just return a permissive marker.
            return hits[0]

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


def _leaf_type_ok(schema: dict) -> bool:
    """Placeholders must resolve to scalar-ish leaves (not objects/arrays)."""
    if not isinstance(schema, dict) or not schema:
        # Unknown/unspecified: allow (best-effort) – schema presence is enforced by lookup.
        return True
    t = schema.get("type")
    if isinstance(t, list):
        # allow if any non-object/array
        return any(x not in ("object", "array") for x in t)
    if t in ("object", "array"):
        return False
    return True


def validate_flow_contract(
    graph_payload: Mapping[str, Any],
    *,
    config_schema: Optional[Mapping[str, Any]] = None,
    config_values: Optional[Mapping[str, Any]] = None,
) -> None:
    """Validate a flow graph against the strict deterministic contract.

    Raises FlowContractError on violations.
    """
    graph = FlowGraph.model_validate(graph_payload)
    trigger_schema = _trigger_input_schema(graph)
    # Internal contract schema for `ctx.*` placeholders/paths.
    try:
        from .internal_contract import compile_ctx_schema
        ctx_schema = compile_ctx_schema(graph_payload)
    except Exception:
        ctx_schema = {}
    config_schema_dict: dict = dict(config_schema or {})
    config_values_obj: Any = dict(config_values or {}) if isinstance(config_values or {}, Mapping) else (config_values or {})

    nodes_by_id: Dict[str, dict] = {
        str(n.id): n.model_dump(mode="python") for n in graph.nodes
    }
    output_schemas: Dict[str, dict] = {}
    for node_id, node in nodes_by_id.items():
        output_schemas[node_id] = _select_output_schema(node)

    rev = _reverse_edges([e.model_dump(mode="python") for e in graph.edges])
    upstream_cache: Dict[str, Set[str]] = {}

    def upstream_of(node_id: str) -> Set[str]:
        if node_id not in upstream_cache:
            upstream_cache[node_id] = _upstream_nodes(rev, node_id)
        return upstream_cache[node_id]

    errors: list[str] = []

    # Validate config values against config schema (publish/arm-time).
    errors.extend(_assert_no_dynamic_config(config_values_obj))
    if config_schema_dict:
        try:
            Draft202012Validator(config_schema_dict).validate(config_values_obj)
        except Exception as exc:
            errors.append(f"config_values do not conform to config_schema: {exc}")
    elif config_values_obj not in (None, {}, []):
        # Values provided with no schema is ambiguous; enforce explicit schema.
        errors.append("config_values provided without config_schema")

    for node_id, node in nodes_by_id.items():
        cfg = node.get("config") or {}
        # Disallow config features that evaluate arbitrary expressions.
        if node.get("kind") == "output_event":
            payload_template = (cfg or {}).get("payload_template")
            if isinstance(payload_template, str) and payload_template.strip() and payload_template.strip() != "{}":
                errors.append(f"{node_id}: output_event.payload_template is not allowed under strict contract")
        for s in _iter_string_values(cfg):
            # Validate embedded placeholders, if any.
            for raw_expr in _find_placeholders(s):
                parsed = _parse_contract_path(raw_expr)
                if parsed.namespace == "input":
                    leaf = _schema_lookup(trigger_schema, parsed.parts)
                    if leaf is None:
                        errors.append(
                            f"{node_id}: placeholder 'input.body.{'.'.join(parsed.parts)}' not in trigger schema"
                        )
                    elif not _leaf_type_ok(leaf):
                        errors.append(
                            f"{node_id}: placeholder 'input.body.{'.'.join(parsed.parts)}' resolves to non-scalar type"
                        )
                elif parsed.namespace == "nodes":
                    ref_node = parsed.node_id or ""
                    if ref_node == node_id:
                        errors.append(f"{node_id}: cannot reference own output via nodes.{ref_node}.output.*")
                        continue
                    if ref_node not in nodes_by_id:
                        errors.append(f"{node_id}: unknown node id referenced: nodes.{ref_node}.output.*")
                        continue
                    if ref_node not in upstream_of(node_id):
                        errors.append(f"{node_id}: nodes.{ref_node}.output.* is not upstream")
                        continue
                    schema = output_schemas.get(ref_node) or {}
                    leaf = _schema_lookup(schema, parsed.parts)
                    if leaf is None:
                        errors.append(
                            f"{node_id}: placeholder 'nodes.{ref_node}.output.{'.'.join(parsed.parts)}' not in output schema"
                        )
                    elif not _leaf_type_ok(leaf):
                        errors.append(
                            f"{node_id}: placeholder 'nodes.{ref_node}.output.{'.'.join(parsed.parts)}' resolves to non-scalar type"
                        )
                elif parsed.namespace == "config":
                    leaf = _schema_lookup(config_schema_dict, parsed.parts)
                    if leaf is None:
                        errors.append(
                            f"{node_id}: placeholder 'config.{'.'.join(parsed.parts)}' not in config_schema"
                        )
                    elif not _leaf_type_ok(leaf):
                        errors.append(
                            f"{node_id}: placeholder 'config.{'.'.join(parsed.parts)}' resolves to non-scalar type"
                        )
                else:
                    leaf = _schema_lookup(ctx_schema, parsed.parts)
                    if leaf is None:
                        errors.append(
                            f"{node_id}: placeholder 'ctx.{'.'.join(parsed.parts)}' not in ctx_schema"
                        )
                    elif not _leaf_type_ok(leaf):
                        errors.append(
                            f"{node_id}: placeholder 'ctx.{'.'.join(parsed.parts)}' resolves to non-scalar type"
                        )

            # Validate direct contract-path strings (common in mapping configs).
            raw = (s or "").strip()
            if _LIKELY_CONTRACT_PATH_RE.match(raw):
                parsed = _parse_contract_path(raw)
                if parsed.namespace == "input":
                    if _schema_lookup(trigger_schema, parsed.parts) is None:
                        errors.append(
                            f"{node_id}: path '{raw}' not in trigger schema"
                        )
                elif parsed.namespace == "nodes":
                    ref_node = parsed.node_id or ""
                    if ref_node not in nodes_by_id:
                        errors.append(f"{node_id}: unknown node id referenced: {raw}")
                    elif ref_node not in upstream_of(node_id):
                        errors.append(f"{node_id}: {raw} is not upstream")
                    elif _schema_lookup(output_schemas.get(ref_node) or {}, parsed.parts) is None:
                        errors.append(f"{node_id}: path '{raw}' not in output schema")
                elif parsed.namespace == "config":
                    if _schema_lookup(config_schema_dict, parsed.parts) is None:
                        errors.append(f"{node_id}: path '{raw}' not in config_schema")
                else:
                    if _schema_lookup(ctx_schema, parsed.parts) is None:
                        errors.append(f"{node_id}: path '{raw}' not in ctx_schema")

    if errors:
        joined = "\n- " + "\n- ".join(errors)
        raise FlowContractError("Flow contract validation failed:" + joined)

