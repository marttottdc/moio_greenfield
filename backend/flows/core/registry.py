# flows/core/registry.py
"""Shared registry for Flow node definitions and executors.

This module provides a single source of truth for both the runtime engine and
the UI builder. A :class:`NodeDefinition` captures every attribute that the
platform needs to know about a node kind (metadata, default config, ports,
form schema, executor, ...). The :class:`NodeRegistry` exposes helpers for
registering and resolving those definitions as well as their executors.

The Django app initialises the registry by calling :func:`register_node`
for each supported node kind. Executors are wired with the
``@register_executor("kind")`` decorator which stores the callable on the same
definition instance. That way ``flows.registry`` (UI) and ``flows.core``
(runtime) always operate on the exact same object graph.
"""

from __future__ import annotations

import inspect
import ipaddress
import json
import logging
import re
import socket
import time
from copy import deepcopy
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Iterable, List, Optional
from urllib.parse import urlparse
from .lib import (
    DotAccessDict,
    _SAFE_BUILTINS,
    _now_iso,
    _resolve_template,
    render_template_string,
    resolve_contract_path,
)
from .formulas import deep_eval_formulas, maybe_eval_formula_string
from flows.core.executors.messaging import send_whatsapp_template
from moio_platform.settings import FLOWS_Q

# Data Lab integrations
from datalab.imports.services import ImportExecutor
from datalab.core.models import (
    Dataset,
    DatasetVersion,
    FileAsset,
    ImportProcess,
    ResultSet,
    ResultSetOrigin,
    ResultSetStorage,  # type: ignore
)
from datalab.core.storage import get_storage

# Flow Scripts
from flows.models import FlowScript, FlowScriptRun, FlowScriptLog
from flows.scripts.param_hydration import resolve_datalab_param_refs
from flows.scripts.tasks import execute_script_run

logger = logging.getLogger(__name__)


_TEMPLATE_PLACEHOLDER_RE = re.compile(r"\{\{\s*(.*?)\s*\}\}")


def _is_single_placeholder_string(value: Any) -> bool:
    """Return True when value is exactly one {{...}} placeholder."""
    if not isinstance(value, str):
        return False

    raw = value.strip()
    matches = list(_TEMPLATE_PLACEHOLDER_RE.finditer(raw))
    return len(matches) == 1 and matches[0].span() == (0, len(raw))


_DATALAB_INGEST_ALLOWED_URL_SCHEMES = {"http", "https"}


def _is_public_network_address(address) -> bool:
    """Return True only for globally routable IP addresses."""
    normalized = address.ipv4_mapped or address
    return bool(getattr(normalized, "is_global", False))


def _resolve_url_host_addresses(hostname: str, port: int):
    try:
        return [ipaddress.ip_address(hostname)]
    except ValueError:
        pass

    addresses = []
    for _, _, _, _, sockaddr in socket.getaddrinfo(hostname, port, type=socket.SOCK_STREAM):
        if not sockaddr:
            continue
        ip_text = sockaddr[0] if isinstance(sockaddr, tuple) else None
        if not ip_text:
            continue
        try:
            addresses.append(ipaddress.ip_address(ip_text))
        except ValueError:
            continue
    return addresses


def _validate_datalab_ingest_url(raw_url: Any) -> str:
    if not isinstance(raw_url, str):
        raise ValueError("URL must be a string")

    candidate = raw_url.strip()
    if not candidate:
        raise ValueError("URL cannot be empty")

    parsed = urlparse(candidate)
    scheme = (parsed.scheme or "").lower()
    if scheme not in _DATALAB_INGEST_ALLOWED_URL_SCHEMES:
        raise ValueError("Only http and https URLs are allowed")

    hostname = parsed.hostname
    if not hostname:
        raise ValueError("URL must include a hostname")

    try:
        parsed_port = parsed.port
    except ValueError as exc:
        raise ValueError("URL has an invalid port") from exc

    port = parsed_port or (443 if scheme == "https" else 80)

    try:
        addresses = _resolve_url_host_addresses(hostname, port)
    except socket.gaierror as exc:
        raise ValueError("URL hostname could not be resolved") from exc

    if not addresses:
        raise ValueError("URL hostname could not be resolved")

    for address in addresses:
        if not _is_public_network_address(address):
            raise ValueError("URL host resolves to a non-public IP address")

    return parsed.geturl()


@dataclass
class PortSpec:
    """Describe a single port available on a node."""

    name: str
    schema: Optional[Dict[str, Any]] = None
    description: Optional[str] = None
    schema_preview: Optional[str] = None


PortMap = Dict[str, List[PortSpec]]
PortBuilder = Callable[["NodeDefinition", Dict[str, Any]], PortMap]


_GENERIC_INPUT_SCHEMA = {
    "type": "object",
    "description": "Incoming JSON payload from the previous node.",
}

_GENERIC_OUTPUT_SCHEMA = {
    "type": "object",
    "description": "Payload emitted by the node to downstream steps.",
}

_TRIGGER_OUTPUT_SCHEMA = {
    "type": "object",
    "description": "Payload generated by the trigger.",
    "properties": {
        "trigger": {"type": "string", "description": "Trigger type"},
        "data": {
            "type": "object",
            "description": "Raw data captured when the trigger fired.",
        },
    },
}


def _serialise_schema(schema: Optional[Dict[str, Any]]) -> Optional[str]:
    if not schema:
        return None
    try:
        return json.dumps(schema, ensure_ascii=False, indent=2)
    except Exception:  # pragma: no cover - defensive
        return json.dumps(schema, ensure_ascii=False)


def _default_port_builder(definition: "NodeDefinition", config: Dict[str, Any]) -> PortMap:
    """Fallback port layout builder used when a node does not provide one."""

    kind = definition.kind
    if kind.startswith("trigger_"):
        return {
            "in": [],
            "out": [
                PortSpec(
                    name="out",
                    schema=deepcopy(_TRIGGER_OUTPUT_SCHEMA),
                    description="Trigger payload",
                    schema_preview=_serialise_schema(_TRIGGER_OUTPUT_SCHEMA),
                )
            ],
        }

    if kind.startswith("output_"):
        return {
            "in": [
                PortSpec(
                    name="in",
                    schema=deepcopy(_GENERIC_INPUT_SCHEMA),
                    description="Payload received from the previous node",
                    schema_preview=_serialise_schema(_GENERIC_INPUT_SCHEMA),
                )
            ],
            "out": [],
        }

    return {
        "in": [
            PortSpec(
                name="in",
                schema=deepcopy(_GENERIC_INPUT_SCHEMA),
                description="Payload received from the previous node",
                schema_preview=_serialise_schema(_GENERIC_INPUT_SCHEMA),
            )
        ],
        "out": [
            PortSpec(
                name="out",
                schema=deepcopy(_GENERIC_OUTPUT_SCHEMA),
                description="Payload emitted by the node",
                schema_preview=_serialise_schema(_GENERIC_OUTPUT_SCHEMA),
            )
        ],
    }


def _branch_port_builder(definition: "NodeDefinition", config: Dict[str, Any]) -> PortMap:
    cfg = config or {}
    rules = cfg.get("rules") or [{"name": "true"}, {"name": "false"}]
    base_schema = {
        "type": "object",
        "description": "Payload that satisfied the branch rule.",
    }
    schema_preview = _serialise_schema(base_schema)
    outputs = [
        PortSpec(
            name=(rule.get("name") or f"rule_{idx + 1}"),
            schema=deepcopy(base_schema),
            description="Branch output",
            schema_preview=schema_preview,
        )
        for idx, rule in enumerate(rules)
    ]
    if cfg.get("else"):
        outputs.append(
            PortSpec(
                name="else",
                schema=deepcopy(base_schema),
                description="Fallback branch",
                schema_preview=schema_preview,
            )
        )

    return {
        "in": [
            PortSpec(
                name="in",
                schema=deepcopy(_GENERIC_INPUT_SCHEMA),
                description="Payload evaluated by the branch",
                schema_preview=_serialise_schema(_GENERIC_INPUT_SCHEMA),
            )
        ],
        "out": outputs,
    }


def _while_port_builder(definition: "NodeDefinition", config: Dict[str, Any]) -> PortMap:
    return {
        "in": [
            PortSpec(
                name="in",
                schema=deepcopy(_GENERIC_INPUT_SCHEMA),
                description="Loop payload",
                schema_preview=_serialise_schema(_GENERIC_INPUT_SCHEMA),
            )
        ],
        "out": [
            PortSpec(
                name="yes",
                schema=deepcopy(_GENERIC_OUTPUT_SCHEMA),
                description="Payload while the condition is true",
                schema_preview=_serialise_schema(_GENERIC_OUTPUT_SCHEMA),
            ),
            PortSpec(
                name="no",
                schema=deepcopy(_GENERIC_OUTPUT_SCHEMA),
                description="Payload when the loop finishes",
                schema_preview=_serialise_schema(_GENERIC_OUTPUT_SCHEMA),
            ),
        ],
    }


_AGENT_INPUT_SCHEMA = {
    "type": "object",
    "description": "Conversation payload provided to the agent.",
    "properties": {
        "message": {"type": "string", "description": "Latest user utterance"},
        "context": {
            "type": "object",
            "description": "Structured context accumulated along the flow.",
        },
        "attachments": {
            "type": "array",
            "items": {"type": "object"},
            "description": "Optional attachments shared with the agent.",
        },
    },
}

_AGENT_OUTPUT_SCHEMA = {
    "type": "object",
    "description": "Result produced by the AI agent (normalized, JSON-safe).",
    "properties": {
        "success": {"type": "boolean"},
        "agent": {"type": "string", "description": "Agent name that executed this node."},
        "turn_id": {"type": ["string", "null"], "description": "FlowAgentTurn id when context tracking is enabled."},
        "output": {
            "description": "Structured output (or text) returned by the agent (best-effort normalized).",
            "type": ["object", "array", "string", "number", "integer", "boolean", "null"],
        },
        "response": {
            "type": ["string", "null"],
            "description": "Best-effort human-readable response (fallback to last assistant message).",
        },
        "messages": {
            "type": "array",
            "description": "Messages emitted during this agent run.",
            "items": {
                "type": "object",
                "properties": {
                    "role": {"type": "string"},
                    "content": {"type": ["string", "null"]},
                },
                "additionalProperties": True,
            },
        },
        "tool_calls": {
            "type": "array",
            "description": "Tool calls requested by the agent during this run (best-effort).",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "args": {"type": ["object", "array", "string", "number", "integer", "boolean", "null"]},
                    "result": {"type": ["object", "array", "string", "number", "integer", "boolean", "null"]},
                    "latency_ms": {"type": ["integer", "null"]},
                },
                "additionalProperties": True,
            },
        },
    },
    "additionalProperties": True,
}


def _agent_port_builder(definition: "NodeDefinition", config: Dict[str, Any]) -> PortMap:
    return {
        "in": [
            PortSpec(
                name="in",
                description="Conversation payload",
                schema=deepcopy(_AGENT_INPUT_SCHEMA),
                schema_preview=_serialise_schema(_AGENT_INPUT_SCHEMA),
            )
        ],
        "out": [
            PortSpec(
                name="out",
                description="Agent response",
                schema=deepcopy(_AGENT_OUTPUT_SCHEMA),
                schema_preview=_serialise_schema(_AGENT_OUTPUT_SCHEMA),
            )
        ],
    }


_HTTP_REQUEST_INPUT_SCHEMA = {
    "type": "object",
    "description": "Parameters for the outgoing HTTP request.",
    "properties": {
        "method": {"type": "string"},
        "url": {"type": "string"},
        "headers": {"type": "object"},
        "body": {"type": "object"},
    },
}

_HTTP_REQUEST_OUTPUT_SCHEMA = {
    "type": "object",
    "description": "HTTP response captured from the remote service.",
    "properties": {
        # NOTE: Runtime executor returns these fields (see `flows/core/executors/http.py`).
        "status_code": {"type": "integer"},
        "response_headers": {"type": "object", "additionalProperties": True},
        "response_data": {
            "anyOf": [
                {"type": "object", "additionalProperties": True},
                {"type": "array", "items": {}},
                {"type": "string"},
                {"type": "number"},
                {"type": "integer"},
                {"type": "boolean"},
                {"type": "null"},
            ]
        },
        "url": {"type": "string"},
        "method": {"type": "string"},

        # Backward-compat aliases (older builders/executors used these names).
        "status": {"type": "integer"},
        "headers": {"type": "object", "additionalProperties": True},
        "body": {
            "anyOf": [
                {"type": "object", "additionalProperties": True},
                {"type": "array", "items": {}},
                {"type": "string"},
                {"type": "number"},
                {"type": "integer"},
                {"type": "boolean"},
                {"type": "null"},
            ]
        },
    },
    "additionalProperties": False,
}


def _schema_ir_to_jsonschema(value: Any) -> dict:
    """
    Convert the builder's lightweight schema IR to JSON Schema.

    The builder currently emits schemas like:
      {"kind":"object","properties":{"foo":{"kind":"primitive","type":"string"}}}

    If the input already looks like JSON Schema (has "type"/"anyOf"/"oneOf"/"allOf"),
    it is returned as-is (best-effort).
    """
    if not isinstance(value, dict):
        return {}

    # Already JSON Schema-ish.
    if any(k in value for k in ("type", "anyOf", "oneOf", "allOf", "$schema")):
        return value

    kind = str(value.get("kind") or "").lower().strip()
    if kind == "primitive":
        t = str(value.get("type") or "").lower().strip()
        if t in {"string", "number", "integer", "boolean", "null"}:
            return {"type": t}
        # "primitive" but unknown -> permissive
        return {}

    if kind == "object":
        props_in = value.get("properties") or {}
        props_out: dict[str, Any] = {}
        if isinstance(props_in, dict):
            for k, v in props_in.items():
                if not isinstance(k, str):
                    continue
                props_out[k] = _schema_ir_to_jsonschema(v)
        return {
            "type": "object",
            "properties": props_out,
            # Default to strict object shape unless the builder explicitly asked otherwise.
            "additionalProperties": bool(value.get("additionalProperties", False)),
        }

    if kind == "array":
        items = _schema_ir_to_jsonschema(value.get("items") or {})
        return {"type": "array", "items": items or {}}

    # Unknown kind -> permissive
    return {}


def _http_response_schema_from_config(config: Dict[str, Any]) -> dict | None:
    """
    Read the optional schema provided by the builder for HTTP responses.

    Convention:
    - config.output_schema describes the JSON structure of `response_data` (not the whole node output envelope).
    """
    raw = (config or {}).get("output_schema")
    if not isinstance(raw, dict) or not raw:
        return None
    schema = _schema_ir_to_jsonschema(raw)
    return schema or None


def _http_request_port_builder(definition: "NodeDefinition", config: Dict[str, Any]) -> PortMap:
    output_schema = deepcopy(_HTTP_REQUEST_OUTPUT_SCHEMA)

    # Allow the builder to provide a response-body schema so publish-time contract validation
    # can validate `nodes.<id>.output.response_data.*` paths.
    response_schema = _http_response_schema_from_config(config or {})
    if response_schema:
        output_schema.setdefault("properties", {})
        output_schema["properties"]["response_data"] = response_schema
        # Also mirror under the legacy alias so older flows can reference `body.*`.
        output_schema["properties"]["body"] = response_schema

    return {
        "in": [
            PortSpec(
                name="in",
                description="HTTP request parameters",
                schema=deepcopy(_HTTP_REQUEST_INPUT_SCHEMA),
                schema_preview=_serialise_schema(_HTTP_REQUEST_INPUT_SCHEMA),
            )
        ],
        "out": [
            PortSpec(
                name="out",
                description="HTTP response payload",
                schema=output_schema,
                schema_preview=_serialise_schema(output_schema),
            )
        ],
    }


_EMAIL_INPUT_SCHEMA = {
    "type": "object",
    "description": "Email envelope to be dispatched.",
    "properties": {
        "to": {"type": "array", "items": {"type": "string"}},
        "subject": {"type": "string"},
        "body": {"type": "string"},
        "attachments": {"type": "array", "items": {"type": "object"}},
    },
}

_EMAIL_OUTPUT_SCHEMA = {
    "type": "object",
    "description": "Delivery status for the sent email.",
    "properties": {
        "message_id": {"type": "string"},
        "status": {"type": "string"},
    },
}


def _email_port_builder(definition: "NodeDefinition", config: Dict[str, Any]) -> PortMap:
    return {
        "in": [
            PortSpec(
                name="in",
                description="Email payload",
                schema=deepcopy(_EMAIL_INPUT_SCHEMA),
                schema_preview=_serialise_schema(_EMAIL_INPUT_SCHEMA),
            )
        ],
        "out": [
            PortSpec(
                name="out",
                description="Email send result",
                schema=deepcopy(_EMAIL_OUTPUT_SCHEMA),
                schema_preview=_serialise_schema(_EMAIL_OUTPUT_SCHEMA),
            )
        ],
    }


_WHATSAPP_INPUT_SCHEMA = {
    "type": "object",
    "description": "WhatsApp message payload.",
    "properties": {
        "to": {"type": "string"},
        "body": {"type": "string"},
        "media": {"type": "array", "items": {"type": "object"}},
    },
}

_WHATSAPP_OUTPUT_SCHEMA = {
    "type": "object",
    "description": "WhatsApp delivery metadata.",
    "properties": {
        "status": {"type": "string"},
        "message_id": {"type": "string"},
    },
}


def _whatsapp_port_builder(definition: "NodeDefinition", config: Dict[str, Any]) -> PortMap:
    return {
        "in": [
            PortSpec(
                name="in",
                description="WhatsApp payload",
                schema=deepcopy(_WHATSAPP_INPUT_SCHEMA),
                schema_preview=_serialise_schema(_WHATSAPP_INPUT_SCHEMA),
            )
        ],
        "out": [
            PortSpec(
                name="out",
                description="WhatsApp send result",
                schema=deepcopy(_WHATSAPP_OUTPUT_SCHEMA),
                schema_preview=_serialise_schema(_WHATSAPP_OUTPUT_SCHEMA),
            )
        ],
    }


def _crm_crud_port_builder(definition: "NodeDefinition", config: Dict[str, Any]) -> PortMap:
    """Ports for the consolidated CRM CRUD node (schema from CRM registry)."""
    cfg = config or {}
    resource_slug = str(cfg.get("resource_slug") or cfg.get("resource") or "").strip().lower()
    operation = str(cfg.get("operation") or cfg.get("op") or "").strip().lower()

    in_schema = deepcopy(_GENERIC_INPUT_SCHEMA)
    out_schema = deepcopy(_GENERIC_OUTPUT_SCHEMA)
    if resource_slug and operation:
        try:
            from crm.contracts import get_resource
            resource = get_resource(resource_slug)
            if resource and operation in resource.operations:
                op_contract = resource.operations[operation]
                in_schema = deepcopy(op_contract.input_schema or in_schema)
                out_schema = deepcopy(op_contract.output_schema or out_schema)
        except Exception:
            pass

    return {
        "in": [
            PortSpec(
                name="in",
                schema=deepcopy(in_schema),
                description="CRM operation input (supports templates like {{ ctx.* }})",
                schema_preview=_serialise_schema(in_schema),
            )
        ],
        "out": [
            PortSpec(
                name="out",
                schema=deepcopy(out_schema),
                description="CRM operation result",
                schema_preview=_serialise_schema(out_schema),
            )
        ],
    }


_CONTACT_INPUT_SCHEMA = {
    "type": "object",
    "description": "Contact attributes to create or update.",
    "properties": {
        "first_name": {"type": "string"},
        "last_name": {"type": "string"},
        "email": {"type": "string"},
        "phone": {"type": "string"},
        "tags": {"type": "array", "items": {"type": "string"}},
    },
}

_CONTACT_OUTPUT_SCHEMA = {
    "type": "object",
    "description": "Result of the contact mutation.",
    "properties": {
        "contact_id": {"type": "string"},
        "status": {"type": "string"},
        "payload": {"type": "object"},
    },
}


def _contact_port_builder(definition: "NodeDefinition", config: Dict[str, Any]) -> PortMap:
    return {
        "in": [
            PortSpec(
                name="in",
                description="Contact payload",
                schema=deepcopy(_CONTACT_INPUT_SCHEMA),
                schema_preview=_serialise_schema(_CONTACT_INPUT_SCHEMA),
            )
        ],
        "out": [
            PortSpec(
                name="out",
                description="Contact action result",
                schema=deepcopy(_CONTACT_OUTPUT_SCHEMA),
                schema_preview=_serialise_schema(_CONTACT_OUTPUT_SCHEMA),
            )
        ],
    }


_TICKET_INPUT_SCHEMA = {
    "type": "object",
    "description": "Ticket payload to create in the CRM.",
    "properties": {
        "title": {"type": "string"},
        "description": {"type": "string"},
        "priority": {"type": "string"},
        "assignee": {"type": "string"},
    },
}

_TICKET_OUTPUT_SCHEMA = {
    "type": "object",
    "description": "Ticket creation result.",
    "properties": {
        "ticket_id": {"type": "string"},
        "status": {"type": "string"},
    },
}


def _ticket_port_builder(definition: "NodeDefinition", config: Dict[str, Any]) -> PortMap:
    return {
        "in": [
            PortSpec(
                name="in",
                description="Ticket payload",
                schema=deepcopy(_TICKET_INPUT_SCHEMA),
                schema_preview=_serialise_schema(_TICKET_INPUT_SCHEMA),
            )
        ],
        "out": [
            PortSpec(
                name="out",
                description="Ticket creation result",
                schema=deepcopy(_TICKET_OUTPUT_SCHEMA),
                schema_preview=_serialise_schema(_TICKET_OUTPUT_SCHEMA),
            )
        ],
    }


_TRANSFORM_OUTPUT_SCHEMA = {
    "type": "object",
    "description": "Structured data produced by the transform node.",
    "properties": {
        "result": {"type": ["object", "array", "string", "number", "boolean"]},
        "logs": {"type": "array", "items": {"type": "string"}},
    },
}


def _transform_port_builder(definition: "NodeDefinition", config: Dict[str, Any]) -> PortMap:
    return {
        "in": [
            PortSpec(
                name="in",
                description="Source payload",
                schema=deepcopy(_GENERIC_INPUT_SCHEMA),
                schema_preview=_serialise_schema(_GENERIC_INPUT_SCHEMA),
            )
        ],
        "out": [
            PortSpec(
                name="out",
                description="Transform result",
                schema=deepcopy(_TRANSFORM_OUTPUT_SCHEMA),
                schema_preview=_serialise_schema(_TRANSFORM_OUTPUT_SCHEMA),
            )
        ],
    }


def _normalize_port_builder(definition: "NodeDefinition", config: Dict[str, Any]) -> PortMap:
    """Port builder for the Normalize node.

    Normalize defines the internal contract. Its output schema is derived from
    the configured mappings and becomes the canonical downstream payload schema.
    """
    cfg = config or {}
    mappings = cfg.get("mappings") or cfg.get("mapping") or []

    def _leaf_schema(type_name: str | None) -> dict:
        t = (type_name or "string").lower().strip()
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

    output_schema: dict = {
        "type": "object",
        "description": "Internal contract produced by Normalize.",
        "properties": {},
        "additionalProperties": False,
    }

    if isinstance(mappings, list):
        for entry in mappings:
            if not isinstance(entry, dict):
                continue
            target = str(entry.get("ctx_path") or entry.get("target") or "").strip()
            if not target.startswith("ctx."):
                continue
            # ctx.event.foo -> ["event","foo"]
            rel = [p for p in target.split(".")[1:] if p]
            if not rel:
                continue
            typ = entry.get("type")
            required = bool(entry.get("required", False))
            _set_schema_path(output_schema, rel, _leaf_schema(typ), required=required)

    return {
        "in": [
            PortSpec(
                name="in",
                schema=deepcopy(_GENERIC_INPUT_SCHEMA),
                description="Raw payload to be normalised",
                schema_preview=_serialise_schema(_GENERIC_INPUT_SCHEMA),
            )
        ],
        "out": [
            PortSpec(
                name="out",
                schema=deepcopy(output_schema),
                description="Normalised internal contract",
                schema_preview=_serialise_schema(output_schema),
            )
        ],
    }


@dataclass
class NodeDefinition:
    """Container for metadata, configuration and runtime behaviour."""

    kind: str
    title: str
    icon: str
    category: str
    enabled: bool = True
    default_config: Dict[str, Any] = field(default_factory=dict)
    description: Optional[str] = None
    form_component: Optional[str] = None
    config_schema: Optional[Any] = None  # Reserved for future Pydantic models
    port_builder: Optional[PortBuilder] = None
    executor: Optional[Callable[..., Any]] = None
    availability: Dict[str, bool] = field(default_factory=dict)
    stages: Dict[str, bool] = field(default_factory=dict)
    hints: Optional[Dict[str, Any]] = None

    def __post_init__(self) -> None:
        """Normalise stage metadata for consistent downstream consumption."""

        stage_flags: Dict[str, bool] = {}
        if self.stages:
            stage_flags = {
                str(name).lower(): bool(value) for name, value in self.stages.items()
            }
        elif self.availability:
            stage_flags = {
                str(name).lower(): bool(value)
                for name, value in self.availability.items()
            }

        # Keep both aliases in sync so callers can use either attribute name.
        self.stages = dict(stage_flags)
        self.availability = dict(stage_flags)

    def stage_flags(self) -> Dict[str, bool]:
        """Return the normalised stage availability map."""

        return dict(self.stages or {})

    def is_stage_limited(self) -> bool:
        flags = self.stage_flags()
        if not flags:
            return False
        enabled = [name for name, allowed in flags.items() if allowed]
        if not enabled:
            return True
        return len(enabled) != len(flags)

    def stage_badge(self) -> Optional[str]:
        """Return a human readable badge when a node targets a specific stage."""

        flags = self.stage_flags()
        if not flags:
            return None
        enabled = [name for name, allowed in flags.items() if allowed]
        if not enabled:
            return "UNAVAILABLE"
        if not self.is_stage_limited():
            return None
        if len(enabled) == 1:
            return enabled[0].upper()
        return ", ".join(name.upper() for name in enabled)

    def is_available_in(self, stage: Optional[str]) -> bool:
        flags = self.stage_flags()
        if not flags:
            return True
        if stage is None:
            return any(flags.values())
        return bool(flags.get(str(stage).lower(), False))

    def compute_ports(self, config: Optional[Dict[str, Any]] = None) -> PortMap:
        builder = self.port_builder or _default_port_builder
        return builder(self, config or {})

    def serialize_ports(self, config: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        port_map = self.compute_ports(config)
        serialised: Dict[str, Any] = {}
        for side, entries in (port_map or {}).items():
            side_entries: List[Dict[str, Any]] = []
            for entry in entries or []:
                if isinstance(entry, PortSpec):
                    side_entries.append(
                        {
                            "name": entry.name,
                            "description": entry.description,
                            "schema": deepcopy(entry.schema),
                            "schema_preview": entry.schema_preview
                            or _serialise_schema(entry.schema),
                        }
                    )
                else:  # pragma: no cover - compatibility path
                    payload = dict(entry)
                    schema = payload.get("schema")
                    payload["schema"] = deepcopy(schema) if schema else None
                    if schema and "schema_preview" not in payload:
                        payload["schema_preview"] = _serialise_schema(schema)
                    side_entries.append(payload)
            serialised[side] = side_entries
        stage_flags = self.stage_flags()
        if stage_flags:
            serialised["meta"] = {"stages": deepcopy(stage_flags)}
        return serialised


class NodeRegistry:
    """Mutable registry mapping node kinds to :class:`NodeDefinition`."""

    def __init__(self) -> None:
        self._definitions: Dict[str, NodeDefinition] = {}

    # --- dictionary-style helpers -------------------------------------------------
    def __contains__(self, kind: str) -> bool:  # pragma: no cover - trivial
        return kind in self._definitions

    def __getitem__(self, kind: str) -> NodeDefinition:
        return self._definitions[kind]

    def items(self):  # pragma: no cover - thin wrapper
        return self._definitions.items()

    # --- public API ----------------------------------------------------------------
    def register(self, definition: NodeDefinition) -> NodeDefinition:
        self._definitions[definition.kind] = definition
        return definition

    def get(self, kind: str) -> Optional[NodeDefinition]:
        return self._definitions.get(kind)

    def all(self) -> Iterable[NodeDefinition]:
        return self._definitions.values()

    def by_category(self) -> Dict[str, List[NodeDefinition]]:
        buckets: Dict[str, List[NodeDefinition]] = {}
        for definition in self._definitions.values():
            buckets.setdefault(definition.category, []).append(definition)
        return buckets

    def register_executor(self, kind: str) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
            definition = self._definitions.get(kind)
            if not definition:
                raise KeyError(f"No node definition registered for kind '{kind}'")
            definition.executor = func
            return func

        return decorator


registry = NodeRegistry()


def register_node(**kwargs: Any) -> NodeDefinition:
    """Register a new node definition and return it for further customisation."""

    definition = NodeDefinition(**kwargs)
    return registry.register(definition)


# ─────────────────────────────────────────────────────────────
# Data Lab Nodes (File Adapter, Promote)
# ─────────────────────────────────────────────────────────────


_DATALAB_IMPORT_OUTPUT_SCHEMA = {
    "type": "object",
    "description": "Result of Data Lab import execution",
    "properties": {
        "resultset_id": {"type": "string"},
        "row_count": {"type": "integer"},
        "schema": {"type": "array"},
    },
}


def _datalab_import_port_builder(definition: "NodeDefinition", config: Dict[str, Any]) -> PortMap:
    return {
        "in": [PortSpec(name="in", description="Import execution request", schema=_GENERIC_INPUT_SCHEMA)],
        "out": [
            PortSpec(
                name="out",
                description="Import execution resultset",
                schema=deepcopy(_DATALAB_IMPORT_OUTPUT_SCHEMA),
                schema_preview=_serialise_schema(_DATALAB_IMPORT_OUTPUT_SCHEMA),
            )
        ],
    }


_DATALAB_PROMOTE_OUTPUT_SCHEMA = {
    "type": "object",
    "description": "Result of promoting a ResultSet to Dataset",
    "properties": {
        "dataset_id": {"type": "string"},
        "version_number": {"type": "integer"},
        "row_count": {"type": "integer"},
    },
}


def _datalab_promote_port_builder(definition: "NodeDefinition", config: Dict[str, Any]) -> PortMap:
    return {
        "in": [PortSpec(name="in", description="Promotion request", schema=_GENERIC_INPUT_SCHEMA)],
        "out": [
            PortSpec(
                name="out",
                description="Dataset promotion result",
                schema=deepcopy(_DATALAB_PROMOTE_OUTPUT_SCHEMA),
                schema_preview=_serialise_schema(_DATALAB_PROMOTE_OUTPUT_SCHEMA),
            )
        ],
    }


_DATALAB_INGEST_OUTPUT_SCHEMA = {
    "type": "object",
    "description": "Result of ingesting a file into Data Lab",
    "properties": {
        "file_id": {"type": "string"},
        "filename": {"type": "string"},
        "content_type": {"type": "string"},
        "size": {"type": "integer"},
        "storage_key": {"type": "string"},
    },
}


def _datalab_ingest_port_builder(definition: "NodeDefinition", config: Dict[str, Any]) -> PortMap:
    return {
        "in": [PortSpec(name="in", description="File source (file_id, url, or content_base64)", schema=_GENERIC_INPUT_SCHEMA)],
        "out": [
            PortSpec(
                name="out",
                description="Created or referenced FileAsset metadata",
                schema=deepcopy(_DATALAB_INGEST_OUTPUT_SCHEMA),
                schema_preview=_serialise_schema(_DATALAB_INGEST_OUTPUT_SCHEMA),
            )
        ],
    }


_DATALAB_RESULTSET_GET_OUTPUT_SCHEMA = {
    "type": "object",
    "description": "ResultSet metadata and optional preview",
    "properties": {
        "resultset_id": {"type": "string"},
        "schema_json": {"type": "object"},
        "row_count": {"type": "integer"},
        "is_json_object": {"type": "boolean"},
        "preview_json": {"type": "array"},
        "storage": {"type": "string"},
        "storage_key": {"type": ["string", "null"]},
        "origin": {"type": "string"},
    },
}


def _datalab_resultset_get_port_builder(definition: "NodeDefinition", config: Dict[str, Any]) -> PortMap:
    return {
        "in": [PortSpec(name="in", description="ResultSet reference", schema=_GENERIC_INPUT_SCHEMA)],
        "out": [
            PortSpec(
                name="out",
                description="ResultSet metadata and optional preview rows",
                schema=deepcopy(_DATALAB_RESULTSET_GET_OUTPUT_SCHEMA),
                schema_preview=_serialise_schema(_DATALAB_RESULTSET_GET_OUTPUT_SCHEMA),
            )
        ],
    }


# --- Node catalog -----------------------------------------------------------------

register_node(
    kind="trigger_manual",
    title="Manual",
    icon="play",
    category="Triggers",
    enabled=False,
)
register_node(
    kind="trigger_webhook",
    title="Webhook",
    icon="webhook",
    category="Triggers",
)
register_node(
    kind="trigger_event",
    title="Event",
    icon="zap",
    category="Triggers",
    default_config={
        "event_name": "",
        "conditions": [],
    },
)
register_node(
    kind="trigger_scheduled",
    title="Scheduled",
    icon="calendar-clock",
    category="Triggers",
    default_config={
        "schedule_type": "cron",
        "cron_expression": "0 9 * * *",
        "interval_seconds": None,
        "run_at": None,
        "timezone": "UTC",
    },
)
register_node(
    kind="trigger_process",
    title="Process",
    icon="cog",
    category="Triggers",
    enabled=False,
)


register_node(
    kind="agent",
    title="AI Agent",
    icon="brain-circuit",
    category="Agents",
    default_config={
        "agent_id": None,
        # Template rendered at runtime (supports {{ctx.*}}).
        "input_message": "{{ctx.workflow.input_as_text}}",
        "input_role": "user",
        "include_chat_history": True,
        "use_flow_session": True,
    },
    port_builder=_agent_port_builder,
)

register_node(
    kind="tool_create_contact",
    title="Create Contact",
    icon="user-plus",
    category="Tools",
    port_builder=_contact_port_builder,
    enabled=False,
)
register_node(
    kind="tool_create_ticket",
    title="Create Ticket",
    icon="ticket",
    category="Tools",
    port_builder=_ticket_port_builder,
    enabled=False,
)

register_node(
    kind="tool_send_whatsapp",
    title="Send WhatsApp",
    icon="message-circle-more",
    category="Tools",
    port_builder=_whatsapp_port_builder,
)

register_node(
    kind="tool_send_whatsapp_template",
    title="WhatsApp Template",
    icon="layout-template",
    category="Tools",
    port_builder=_whatsapp_port_builder,
    default_config={
        "template": None,
        "mapping": {},
        "atomic_options": {
            "save_contact": False,
            "contact_fullname": None,
            "contact_type_id": None,
            "notify_agent": False,
            "flow_context": None,
        },
    },
)
register_node(
    kind="tool_send_email",
    title="Send Email",
    icon="send",
    category="Tools",
    port_builder=_email_port_builder,
)
register_node(
    kind="tool_http_request",
    title="HTTP Request",
    icon="cable",
    category="Tools",
    port_builder=_http_request_port_builder,
)

register_node(
    kind="tool_crm_crud",
    title="CRM CRUD",
    icon="database",
    category="Tools",
    port_builder=_crm_crud_port_builder,
    default_config={
        "resource_slug": "contact",
        "operation": "create",
        "input": {},
    },
    hints={
        "description": "Consolidated CRM node. Select a CRM resource and operation; configure input from ctx via templates.",
        "registry_endpoints": {
            "models": "/api/v1/flows/crm/models/",
            "detail": "/api/v1/flows/crm/{slug}/",
        },
        "tips": (
            "Use {{ctx.*}} placeholders for input values. Operation schemas are provided by the CRM registry endpoints. "
            "After execution, last result is available at ctx.crm.<resource>.last (alias: ctx.last.crm.<resource>), "
            "e.g. Branch on ctx.crm.contact.last.email or ctx.crm.deal.last.status."
        ),
    },
)
register_node(
    kind="tool_update_candidate",
    title="Update Candidate",
    icon="user-pen",
    category="Tools",
    port_builder=_contact_port_builder,
    enabled=False,
)

register_node(
    kind="logic_normalize",
    title="Normalize",
    icon="file-json",
    category="Logic",
    port_builder=_normalize_port_builder,
    default_config={
        "mappings": [],
        "fail_on_missing_required": True,
    },
    hints={
        "description": "Transforms external input into a stable internal contract. This node defines the contract used by downstream logic.",
        "example_config": {
            "mappings": [
                {"ctx_path": "ctx.event.tipo_nombre", "source_path": "input.body.values.tipo_nombre", "type": "string", "required": True},
                {"ctx_path": "ctx.event.whatsapp_number", "source_path": "input.body.values.whatsapp_number", "type": "string", "required": True},
            ],
            "fail_on_missing_required": True,
        },
        "tips": "Downstream Branch/Condition/While expressions can only read ctx.*. Use this node to create ctx.event.* first.",
    },
)

register_node(
    kind="logic_branch",
    title="Branch",
    icon="split",
    category="Logic",
    port_builder=_branch_port_builder,
    default_config={"rules": [{"name": "true"}, {"name": "false"}], "else": False},
    hints={
        "description": "Routes execution to different paths based on multiple rules. Evaluates rules in order and routes to the first matching branch.",
        "example_config": {
            "rules": [
                {"name": "high_priority", "expr": "ctx.event.priority == 'high'"},
                {"name": "medium_priority", "expr": "ctx.event.priority == 'medium'"},
                {"name": "low_priority", "expr": "ctx.event.priority == 'low'"}
            ],
            "else": True
        },
        "use_cases": [
            "Route tickets based on priority level",
            "Direct leads to different sales reps based on territory",
            "Send different email templates based on customer segment",
            "Handle multiple outcomes from a single decision point"
        ],
        "expression_examples": [
            {"expr": "ctx.event.status == 'active'", "description": "Check if status equals a value"},
            {"expr": "ctx.event.amount > 1000", "description": "Compare numeric values"},
            {"expr": "ctx.event.segment == 'premium'", "description": "Access nested fields"}
        ],
        "tips": "Rules are evaluated top-to-bottom. The first matching rule wins. Expressions are sandboxed and can only read ctx.* (no payload/input). Enable 'else' for a fallback when no rules match."
    },
)
register_node(
    kind="logic_condition",
    title="Condition",
    icon="circle-help",
    category="Logic",
    hints={
        "description": "Simple true/false branching based on a single expression. Routes to 'true' or 'false' output port.",
        "example_config": {
            "expr": "ctx.event.deal_value > 10000"
        },
        "use_cases": [
            "Check if a deal exceeds a threshold value",
            "Verify if a contact has a valid email",
            "Determine if a ticket needs escalation",
            "Filter events based on a single criterion"
        ],
        "expression_examples": [
            {"expr": "ctx.event.is_verified == True", "description": "Check boolean flag"},
            {"expr": "ctx.event.email is not None", "description": "Check if field exists"},
            {"expr": "ctx.event.age >= 18 and ctx.event.country == 'US'", "description": "Combine conditions with and/or"}
        ],
        "tips": "Use this for simple yes/no decisions. Expressions are sandboxed and can only read ctx.*. For multiple outcomes, use Branch instead."
    },
)
register_node(
    kind="logic_while",
    title="While",
    icon="repeat",
    category="Logic",
    port_builder=_while_port_builder,
    default_config={"expr": "True"},
    hints={
        "description": "Repeats connected nodes while a condition is true. Use for retry logic, pagination, or iterating over lists.",
        "example_config": {
            "expr": "ctx.loop.retry_count < 3",
            "max_iterations": 10
        },
        "use_cases": [
            "Retry failed API calls up to N times",
            "Paginate through API results until no more pages",
            "Process items in a list one by one",
            "Poll for status until complete or timeout"
        ],
        "expression_examples": [
            {"expr": "ctx.loop.retry_count < 5", "description": "Retry up to 5 times"},
            {"expr": "ctx.loop.has_more_pages == True", "description": "Continue while pagination flag is set"},
            {"expr": "ctx.event.status != 'completed'", "description": "Loop until status changes"}
        ],
        "tips": "Always set max_iterations to prevent infinite loops. Expressions are sandboxed and can only read ctx.*."
    },
)
register_node(
    kind="transform",
    title="Transform",
    icon="wand-2",
    category="Logic",
    port_builder=_transform_port_builder,
    enabled=False,
)

register_node(
    kind="data_set_values",
    title="Set Values",
    icon="file-input",
    category="Data",
    description="Inject fixed key-value pairs into the data flow. Values are passed to downstream nodes as input.",
    enabled=False,
    default_config={
        "values": [],
        "merge_with_input": False,
    },
    hints={
        "description": "Define fixed key-value pairs that become available to downstream nodes. Useful for injecting constants, configuration, or default values.",
        "example_config": {
            "values": [
                {"key": "api_version", "value": "v2"},
                {"key": "max_retries", "value": "3"},
                {"key": "default_status", "value": "pending"}
            ],
            "merge_with_input": True
        },
        "use_cases": [
            "Inject configuration values for downstream API calls",
            "Set default values for processing",
            "Define constants used across multiple nodes",
            "Pass fixed parameters to agents or tools"
        ],
        "tips": "Enable 'merge_with_input' to combine these values with the incoming payload. Values can use expressions like {{payload.field}} for dynamic content."
    },
)

register_node(
    kind="data_formula",
    title="Formula",
    icon="calculator",
    category="Tools",
    description="Transform data using formulas: combine values, string operations, math, and date/time functions.",
    enabled=False,
    default_config={
        "formulas": [],
        "merge_with_input": False,
    },
    hints={
        "description": "Create new values by combining upstream data with formulas. Supports string manipulation, numeric operations, and date/time functions.",
        "example_config": {
            "formulas": [
                {"key": "full_name", "expr": "concat(payload.first_name, ' ', payload.last_name)"},
                {"key": "total", "expr": "payload.price * payload.quantity"},
                {"key": "created_at", "expr": "now()"},
                {"key": "due_date", "expr": "date_add(now(), 7, 'days')"}
            ],
            "merge_with_input": True
        },
        "use_cases": [
            "Combine first and last name into full name",
            "Calculate totals, discounts, or percentages",
            "Generate timestamps or due dates",
            "Format strings for display or API calls"
        ],
        "available_functions": {
            "string": ["concat(...)", "upper(s)", "lower(s)", "trim(s)", "replace(s, old, new)", "substring(s, start, end)", "length(s)", "split(s, sep)"],
            "numeric": ["round(n, decimals)", "floor(n)", "ceil(n)", "abs(n)", "min(...)", "max(...)", "sum(...)"],
            "datetime": ["now()", "today()", "date_add(date, amount, unit)", "date_diff(date1, date2, unit)", "format_date(date, format)", "parse_date(s, format)"],
            "logic": ["if_else(condition, true_val, false_val)", "coalesce(...)", "is_null(val)", "is_empty(val)"]
        },
        "tips": "Access upstream values with payload.field. Formulas are Python-like expressions. Date units: 'days', 'hours', 'minutes', 'seconds'."
    },
)

# --- Data Lab Nodes ---------------------------------------------------------
register_node(
    kind="datalab_file_adapter",
    title="Data Lab Import",
    icon="file-input",
    category="Data Lab",
    port_builder=_datalab_import_port_builder,
    default_config={
        "import_process_id": None,
        "source": {},  # {"file_id": "..."} or {"fileset_id": "..."}
        "materialize": False,
    },
    form_component="datalab-file-adapter-form",
    hints={
        "description": "Execute a Data Lab ImportProcess (File Adapter) to produce a normalized ResultSet.",
    },
)

register_node(
    kind="datalab_promote",
    title="Promote to Dataset",
    icon="database-plus",
    category="Data Lab",
    port_builder=_datalab_promote_port_builder,
    default_config={
        "resultset_id": None,
        "dataset_id": None,  # optional existing dataset
        "dataset_name": None,  # used when creating a new dataset
        "mode": "new_version",  # replace | new_version | append
        "description": "",
    },
    form_component="datalab-promote-form",
    hints={
        "description": "Promote a ResultSet to a Dataset (create or new version).",
    },
)

register_node(
    kind="datalab_ingest",
    title="Ingest File",
    icon="upload",
    category="Data Lab",
    port_builder=_datalab_ingest_port_builder,
    default_config={
        "file_id": None,
        "url": None,
        "content_base64": None,
        "filename": None,
        "content_type": None,
    },
    form_component="datalab-ingest-form",
    hints={
        "description": "Create a Data Lab FileAsset from file_id, URL, or inline base64 content.",
    },
)

register_node(
    kind="datalab_resultset_get",
    title="Get ResultSet",
    icon="table",
    category="Data Lab",
    port_builder=_datalab_resultset_get_port_builder,
    default_config={
        "resultset_id": None,
        "include_preview": True,
        "preview_limit": 200,
    },
    form_component="datalab-resultset-get-form",
    hints={
        "description": "Fetch ResultSet metadata and optional preview (for use in flows; bypasses API fencing).",
    },
)

# --- Script Node -------------------------------------------------------------
register_node(
    kind="flow_script",
    title="Flow Script",
    icon="file-code",
    category="Tools",
    default_config={
        "script_id": None,
        "version_id": None,
        "input_payload": {},
    },
    form_component="flow-script-form",
    hints={
        "description": "Execute a stored Flow Script (optionally specify a version).",
    },
)

# --- Control Nodes -----------------------------------------------------------
register_node(
    kind="delay",
    title="Delay / Wait",
    icon="clock",
    category="Control",
    default_config={
        "seconds": 5,
    },
    form_component="delay-form",
    hints={
        "description": "Pause execution for a number of seconds before continuing.",
    },
)

register_node(
    kind="output_function",
    title="Function",
    icon="code",
    category="Outputs",
    hints={
        "description": (
            "Terminal output node for previews and synchronous runs. "
            "It records the incoming payload into ctx['$outputs'] as a 'function' output. "
            "It does not execute arbitrary Python code by itself."
        ),
        "use_cases": [
            "Mark the end of a path and inspect the final payload in preview",
            "Collect one or more outputs from different branches",
        ],
        "tips": "If you need to run code, use Flow Script or a Tool node. This node only records outputs.",
    },
)
register_node(
    kind="output_task",
    title="Celery Task",
    icon="list-todo",
    category="Outputs",
    enabled=False,
    form_component="output-task-form",
)
register_node(
    kind="output_event",
    title="Emit Event",
    icon="megaphone",
    category="Outputs",
    default_config={
        "event_name": "",
        "payload_template": "{}",
    },
    form_component="output-event-form",
)
register_node(
    kind="output_webhook_reply",
    title="Webhook Reply",
    icon="reply",
    category="Outputs",
    enabled=False,
    form_component="output-webhook-reply-form",
)
register_node(
    kind="output_agent",
    title="Agent Output",
    icon="message-square-reply",
    category="Outputs",
    enabled=False,
    form_component="output-agent-form",
)

# 1. Register the node definition (shows up in the UI)
register_node(
    kind="debug_logger",
    title="Log Message",
    icon="scroll-text",
    category="Debug",
    form_component="debug-logger-form",
    description="Write a message to the application log (and optionally to flow context)",
    default_config={
        "level": "INFO",          # choices: DEBUG, INFO, WARNING, ERROR
        "message": "Hello from {{payload}}",  # Jinja2-style, will be evaluated
        "include_payload": True,
        "store_in_context": False,
        "context_key": "last_log",
    },
    enabled=False,
)

# --- Runtime execution helpers -----------------------------------------------------


def register_executor(kind: str) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    return registry.register_executor(kind)


def get_executor(kind: str) -> Callable[..., Any]:
    definition = registry.get(kind)
    if definition and definition.executor:
        return definition.executor
    return default_executor


def default_executor(node: Dict[str, Any], payload: Dict[str, Any], ctx: Dict[str, Any]) -> Dict[str, Any]:
    """Fallback executor if no handler is registered for this kind."""

    print(f"[flows.registry] No executor registered for kind={node.get('kind')}")
    return {"echo": payload}


# ---------------------------------------------------------------------
#  TRIGGERS
# ---------------------------------------------------------------------


@register_executor("trigger_manual")
def _trig_manual(node, payload, ctx):
    """Triggered manually (user click or API)."""

    config = node.get("config", {})

    if config:
        return config
    else:
        return payload


@register_executor("trigger_process")
def _trig_process(node, payload, ctx):
    """Triggered by another internal process or flow."""

    return payload


@register_executor("trigger_webhook")
def _trig_webhook(node, payload, ctx):
    """Triggered by an incoming webhook."""

    return payload


@register_executor("trigger_event")
def _trig_event(node, payload, ctx):
    """Triggered by an event bus message."""

    return payload


@register_executor("trigger_scheduled")
def _trig_scheduled(node, payload, ctx):
    """Triggered by a cron/scheduler."""

    return payload


@register_executor("logic_normalize")
def _logic_normalize(node: dict, payload: Any, ctx: dict) -> dict:
    """Normalize external inputs into an internal contract.

    Reads values via strict contract paths (input.body.*, nodes.<id>.output.*, config.*)
    and writes them into ctx.* (runtime context), then returns the normalised
    object as the downstream payload.
    """
    import re

    config = node.get("config", {}) or {}
    mappings = config.get("mappings") or config.get("mapping") or []
    fail_on_missing_required = bool(config.get("fail_on_missing_required", True))

    ctx_path_re = re.compile(r"^ctx\.[A-Za-z0-9_-]+(\.[A-Za-z0-9_-]+)*$")

    def _set_nested(obj: dict, parts: list[str], value: Any) -> None:
        cur = obj
        for part in parts[:-1]:
            nxt = cur.get(part)
            if not isinstance(nxt, dict):
                nxt = {}
                cur[part] = nxt
            cur = nxt
        cur[parts[-1]] = value

    def _assert_type(value: Any, type_name: Any) -> None:
        if value is None:
            return
        t = str(type_name or "string").lower().strip()
        if t in {"string", "str"}:
            if not isinstance(value, str):
                raise ValueError(f"expected string, got {type(value).__name__}")
            return
        if t in {"number", "float"}:
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise ValueError(f"expected number, got {type(value).__name__}")
            return
        if t in {"integer", "int"}:
            if isinstance(value, bool) or not isinstance(value, int):
                raise ValueError(f"expected integer, got {type(value).__name__}")
            return
        if t in {"boolean", "bool"}:
            if not isinstance(value, bool):
                raise ValueError(f"expected boolean, got {type(value).__name__}")
            return
        if t in {"object", "dict"}:
            if not isinstance(value, dict):
                raise ValueError(f"expected object, got {type(value).__name__}")
            return
        if t in {"array", "list"}:
            if not isinstance(value, list):
                raise ValueError(f"expected array, got {type(value).__name__}")
            return
        # Unknown type label: treat as string
        if not isinstance(value, str):
            raise ValueError(f"expected string, got {type(value).__name__}")

    normalised: dict = {}
    if not isinstance(mappings, list):
        return normalised

    for idx, entry in enumerate(mappings):
        if not isinstance(entry, dict):
            continue
        target = str(entry.get("ctx_path") or entry.get("target") or "").strip()
        if not target or not ctx_path_re.match(target):
            raise ValueError(f"Invalid ctx_path in mapping[{idx}] (expected 'ctx.<field>...')")
        rel_parts = [p for p in target.split(".")[1:] if p]
        if not rel_parts:
            raise ValueError(f"Invalid ctx_path in mapping[{idx}] (missing destination)")
        reserved_roots = {
            "config",
            "nodes",
            "$input",
            "$trigger",
            "$outputs",
            "$loops",
            "$sandbox",
            "tenant_id",
            "execution_id",
            "flow_execution_id",
        }
        if rel_parts[0].startswith("$") or rel_parts[0] in reserved_roots:
            raise ValueError(
                f"Invalid ctx_path root '{rel_parts[0]}' in mapping[{idx}] (reserved runtime key)"
            )

        source_path = entry.get("source_path") or entry.get("source") or entry.get("path")
        required = bool(entry.get("required", False))
        default_value = entry.get("default", None)
        type_name = entry.get("type")

        value = None
        if source_path not in (None, ""):
            raw_source = str(source_path).strip()
            # Opt-in formula source: "=..." is evaluated in strict-contract scope.
            if raw_source.startswith("="):
                value = maybe_eval_formula_string(raw_source, context=ctx)
            else:
                try:
                    value = resolve_contract_path(raw_source, ctx)
                except Exception:
                    value = None

        if value is None and default_value is not None:
            value = default_value

        if value is None and required and fail_on_missing_required:
            raise ValueError(f"Missing required value for {target} from source '{source_path}'")

        # Type check (fail-fast)
        try:
            _assert_type(value, type_name)
        except Exception as exc:
            raise ValueError(f"Type mismatch for {target}: {exc}") from exc

        if value is None and not required:
            # Optional missing value: do not write it.
            continue

        # Write to ctx (context) under rel path, and build output payload.
        _set_nested(ctx, rel_parts, value)
        _set_nested(normalised, rel_parts, value)

    return normalised


@register_executor("debug_logger")
def debug_logger(node: dict, payload: Any, context: dict) -> dict:
    config = node.get("config", {})
    level = config.get("level", "INFO").upper()
    message_template = config.get("message", "")
    include_payload = config.get("include_payload", True)
    store_in_context = config.get("store_in_context", False)
    context_key = config.get("context_key", "last_log")

    # Simple expression evaluation (same safe scope the engine uses)
    scope = {"payload": payload, "ctx": context, "context": context}
    try:

        message = eval(f"f'''{message_template}'''", {"__builtins__": _SAFE_BUILTINS}, scope)
    except Exception:
        message = message_template  # fallback if templating fails

    final_message = message
    if include_payload and payload is not None:
        final_message = f"{message} | payload={payload}"

    # Actual logging
    getattr(logger, level.lower())(final_message, extra={
        "node_id": node.get("id"),
        "node_name": node.get("name"),
        "tenant_id": context.get("tenant_id"),
    })

    result = {
        "logged_at": _now_iso(),
        "level": level,
        "message": final_message,
    }

    if store_in_context:
        context[context_key] = result

    return result


def _build_formula_scope(payload: Any, context: dict) -> dict:
    """Build the scope with all available formula functions."""
    from datetime import datetime, timedelta
    from django.utils.timezone import now as django_now
    
    def concat(*args):
        return "".join(str(a) for a in args if a is not None)
    
    def upper(s):
        return str(s).upper() if s else ""
    
    def lower(s):
        return str(s).lower() if s else ""
    
    def trim(s):
        return str(s).strip() if s else ""
    
    def replace(s, old, new):
        return str(s).replace(old, new) if s else ""
    
    def substring(s, start, end=None):
        s = str(s) if s else ""
        return s[start:end] if end else s[start:]
    
    def length(s):
        return len(s) if s else 0
    
    def split(s, sep=" "):
        return str(s).split(sep) if s else []
    
    def _round(n, decimals=0):
        try:
            return round(float(n), int(decimals))
        except (ValueError, TypeError):
            return n
    
    def floor(n):
        import math
        try:
            return math.floor(float(n))
        except (ValueError, TypeError):
            return n
    
    def ceil(n):
        import math
        try:
            return math.ceil(float(n))
        except (ValueError, TypeError):
            return n
    
    def _abs(n):
        try:
            return abs(float(n))
        except (ValueError, TypeError):
            return n
    
    def _min(*args):
        nums = [float(a) for a in args if a is not None]
        return min(nums) if nums else None
    
    def _max(*args):
        nums = [float(a) for a in args if a is not None]
        return max(nums) if nums else None
    
    def _sum(*args):
        nums = [float(a) for a in args if a is not None]
        return sum(nums)
    
    def now():
        return django_now().isoformat()
    
    def today():
        return django_now().date().isoformat()
    
    def date_add(date_str, amount, unit="days"):
        try:
            if isinstance(date_str, str):
                dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
            else:
                dt = date_str
            amount = int(amount)
            if unit == "days":
                result = dt + timedelta(days=amount)
            elif unit == "hours":
                result = dt + timedelta(hours=amount)
            elif unit == "minutes":
                result = dt + timedelta(minutes=amount)
            elif unit == "seconds":
                result = dt + timedelta(seconds=amount)
            elif unit == "weeks":
                result = dt + timedelta(weeks=amount)
            else:
                result = dt + timedelta(days=amount)
            return result.isoformat()
        except Exception:
            return date_str
    
    def date_diff(date1, date2, unit="days"):
        try:
            if isinstance(date1, str):
                dt1 = datetime.fromisoformat(date1.replace("Z", "+00:00"))
            else:
                dt1 = date1
            if isinstance(date2, str):
                dt2 = datetime.fromisoformat(date2.replace("Z", "+00:00"))
            else:
                dt2 = date2
            diff = dt1 - dt2
            if unit == "days":
                return diff.days
            elif unit == "hours":
                return diff.total_seconds() / 3600
            elif unit == "minutes":
                return diff.total_seconds() / 60
            elif unit == "seconds":
                return diff.total_seconds()
            return diff.days
        except Exception:
            return 0
    
    def format_date(date_str, fmt="%Y-%m-%d"):
        try:
            if isinstance(date_str, str):
                dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
            else:
                dt = date_str
            return dt.strftime(fmt)
        except Exception:
            return date_str
    
    def parse_date(s, fmt="%Y-%m-%d"):
        try:
            return datetime.strptime(s, fmt).isoformat()
        except Exception:
            return s
    
    def if_else(condition, true_val, false_val):
        return true_val if condition else false_val
    
    def coalesce(*args):
        for a in args:
            if a is not None and a != "":
                return a
        return None
    
    def is_null(val):
        return val is None
    
    def is_empty(val):
        if val is None:
            return True
        if isinstance(val, str) and val.strip() == "":
            return True
        if isinstance(val, (list, dict)) and len(val) == 0:
            return True
        return False
    
    payload_view = DotAccessDict(payload) if isinstance(payload, dict) else payload
    ctx_view = DotAccessDict(context) if isinstance(context, dict) else context

    return {
        # Dot-access convenience for builder UX (payload.first_name) while still
        # supporting dict-style access (payload["first_name"] / payload.get(...)).
        "payload": payload_view,
        "ctx": ctx_view,
        "context": ctx_view,
        "concat": concat,
        "upper": upper,
        "lower": lower,
        "trim": trim,
        "replace": replace,
        "substring": substring,
        "length": length,
        "split": split,
        "round": _round,
        "floor": floor,
        "ceil": ceil,
        "abs": _abs,
        "min": _min,
        "max": _max,
        "sum": _sum,
        "now": now,
        "today": today,
        "date_add": date_add,
        "date_diff": date_diff,
        "format_date": format_date,
        "parse_date": parse_date,
        "if_else": if_else,
        "coalesce": coalesce,
        "is_null": is_null,
        "is_empty": is_empty,
        "True": True,
        "False": False,
        "None": None,
        "int": int,
        "float": float,
        "str": str,
        "len": len,
        "bool": bool,
    }


@register_executor("data_formula")
def data_formula_executor(node: dict, payload: Any, context: dict) -> dict:
    """
    Transform data using formulas with string, numeric, and date/time functions.
    
    Config:
        formulas: List of {key: str, expr: str} objects
        merge_with_input: If True, merge with incoming payload
    
    Returns:
        Dict with computed values (optionally merged with input)
    """
    config = node.get("config", {})
    formulas_list = config.get("formulas", [])
    merge_with_input = config.get("merge_with_input", False)
    
    result = {}
    
    if merge_with_input and isinstance(payload, dict):
        result = dict(payload)
    
    scope = _build_formula_scope(payload, context)
    
    for item in formulas_list:
        if not isinstance(item, dict):
            continue
        key = item.get("key", "")
        expr = item.get("expr", "")
        
        if not key or not expr:
            continue
        
        try:
            value = eval(expr, {"__builtins__": {}}, scope)
            result[key] = value
        except Exception as e:
            result[key] = f"#ERROR: {str(e)}"
    
    return result


@register_executor("data_set_values")
def data_set_values_executor(node: dict, payload: Any, context: dict) -> dict:
    """
    Inject fixed key-value pairs into the data flow.
    
    Config:
        values: List of {key: str, value: str} objects
        merge_with_input: If True, merge with incoming payload; if False, return only these values
    
    Returns:
        Dict with all key-value pairs (optionally merged with input payload)
    """
    config = node.get("config", {})
    values_list = config.get("values", [])
    merge_with_input = config.get("merge_with_input", False)
    
    result = {}
    
    if merge_with_input and isinstance(payload, dict):
        result = dict(payload)
    
    scope = {"payload": payload, "ctx": context, "context": context}
    
    for item in values_list:
        if not isinstance(item, dict):
            continue
        key = item.get("key", "")
        value = item.get("value", "")
        
        if not key:
            continue
        
        if isinstance(value, str) and ("{{" in value or "{%" in value):
            try:
                evaluated = eval(f"f'''{value.replace('{{', '{').replace('}}', '}')}'''", {"__builtins__": _SAFE_BUILTINS}, scope)
                result[key] = evaluated
            except Exception:
                result[key] = value
        else:
            result[key] = value
    
    return result


# ---------------------------------------------------------------------
#  PLATFORM TOOLS
# ---------------------------------------------------------------------


def _record_tool_failure(ctx: Dict[str, Any], node: Dict[str, Any], payload: Any, error: str) -> None:
    entry = {
        "node_id": node.get("id"),
        "node_name": node.get("name"),
        "kind": node.get("kind"),
        "error": error,
        "input": payload,
    }
    ctx.setdefault("$tool_failures", []).append(entry)


def _tool_executor(helper_name: str) -> Callable[[Dict[str, Any], Dict[str, Any], Dict[str, Any]], Dict[str, Any]]:
    def executor(node: Dict[str, Any], payload: Dict[str, Any], ctx: Dict[str, Any]) -> Dict[str, Any]:
        from . import platform_tools  # Imported lazily for testability

        tool_fn = getattr(platform_tools, helper_name)
        signature = inspect.signature(tool_fn)
        accepts_kwargs = any(
            parameter.kind == inspect.Parameter.VAR_KEYWORD
            for parameter in signature.parameters.values()
        )
        allowed_params = set(signature.parameters.keys())

        kwargs: Dict[str, Any] = {}
        config = node.get("config")
        if isinstance(config, dict):
            kwargs.update(config)
        if isinstance(payload, dict):
            kwargs.update(payload)
        else:
            kwargs.setdefault("payload", payload)

        if not accepts_kwargs:
            kwargs = {k: v for k, v in kwargs.items() if k in allowed_params}

        tenant_id = ctx.get("tenant_id")
        if tenant_id is not None and (accepts_kwargs or "tenant_id" in allowed_params):
            kwargs.setdefault("tenant_id", tenant_id)

        # Evaluate any '=...' formula strings in tool arguments (strict contract scope).
        # This allows formula-capable fields everywhere a tool accepts text inputs.
        kwargs = deep_eval_formulas(kwargs, context=ctx)

        # Template rendering for user-facing strings (subject/body) for email tool.
        # HTML bodies are auto-escaped by default; use safe(...) to opt out.
        if helper_name == "send_email":
            body_template = kwargs.get("body")
            body_is_html = (
                isinstance(body_template, str)
                and "<" in body_template
                and ">" in body_template
                and "</" in body_template
            )

            if "to" in kwargs:
                to_value = kwargs.get("to")
                if isinstance(to_value, list):
                    kwargs["to"] = [render_template_string(item, payload, ctx) for item in to_value]
                else:
                    kwargs["to"] = render_template_string(to_value, payload, ctx)

            if "from_email" in kwargs:
                kwargs["from_email"] = render_template_string(kwargs.get("from_email"), payload, ctx)

            if "subject" in kwargs:
                kwargs["subject"] = render_template_string(kwargs.get("subject"), payload, ctx)

            if "body" in kwargs:
                kwargs["body"] = render_template_string(
                    kwargs.get("body"),
                    payload,
                    ctx,
                    autoescape_html=body_is_html,
                )

        try:
            result = tool_fn(**kwargs)
        except Exception as exc:  # pragma: no cover - exercised via tests
            error_message = str(exc) or exc.__class__.__name__
            failure = {"success": False, "error": error_message, "exception": repr(exc)}
            _record_tool_failure(ctx, node, payload, error_message)
            return failure

        if not isinstance(result, dict):
            result = {"success": True, "result": result}

        success_flag = result.get("success")
        if success_flag is False or (success_flag is None and result.get("error")):
            _record_tool_failure(ctx, node, payload, str(result.get("error")))

        return result

    return executor


def _lookup_mapping_path(payload: Any, ctx: Dict[str, Any], path: Any) -> Any:
    """Resolve a contract path for mapping fields.

    Strict contract: `input.body.*`, `nodes.<nodeId>.output.*`, `config.*`, and `ctx.*`.
    """
    if path is None:
        return None
    if isinstance(path, (int, float, bool)):
        return path
    raw = str(path).strip()
    if not raw:
        return None
    # Allow inline strict-contract formulas for any mapping field.
    if raw.startswith("="):
        return maybe_eval_formula_string(raw, context=ctx)
    try:
        return resolve_contract_path(raw, ctx)
    except Exception:
        return None


def _resolve_mapping_entry(entry: Any, payload: Any, ctx: Dict[str, Any]) -> Any:
    if entry is None:
        return None
    if isinstance(entry, (int, float, bool)):
        return entry
    if isinstance(entry, str):
        return _lookup_mapping_path(payload, ctx, entry)
    if isinstance(entry, dict):
        mode = str(entry.get("mode") or entry.get("source") or "field").lower()
        if mode in {"literal", "fixed", "static"}:
            return entry.get("value")
        path = entry.get("path")
        if path is None or path == "":
            path = entry.get("value") or entry.get("field")
        return _lookup_mapping_path(payload, ctx, path)
    return None


_TOOL_EXECUTORS = {
    "tool_create_contact": _tool_executor("create_crm_contact"),
    "tool_create_ticket": _tool_executor("create_crm_ticket"),
    "tool_send_whatsapp": _tool_executor("send_whatsapp_message"),
    "tool_send_email": _tool_executor("send_email"),
    "tool_http_request": _tool_executor("http_request"),
    "tool_update_candidate": _tool_executor("update_candidate_status"),
}


def _sandbox_result(action: str, simulated_data: dict) -> dict:
    """Return a simulated sandbox result."""
    return {
        "success": True,
        "sandbox": True,
        "sandbox_action": action,
        **simulated_data,
    }


@register_executor("tool_create_contact")
def _tool_create_contact(node, payload, ctx):
    if ctx.get("$sandbox"):
        config = node.get("config", {}) or {}
        name = config.get("name") or payload.get("name", "Unknown")
        phone = config.get("phone") or payload.get("phone", "")
        return _sandbox_result(
            f"Create contact: {name}",
            {
                "contact_id": "sandbox-contact-001",
                "name": name,
                "phone": phone,
                "message": "Contact created (simulated)",
            }
        )
    return _TOOL_EXECUTORS["tool_create_contact"](node, payload, ctx)


@register_executor("tool_create_ticket")
def _tool_create_ticket(node, payload, ctx):
    if ctx.get("$sandbox"):
        config = node.get("config", {}) or {}
        title = config.get("title") or payload.get("title", "New Ticket")
        return _sandbox_result(
            f"Create ticket: {title}",
            {
                "ticket_id": "sandbox-ticket-001",
                "title": title,
                "status": "open",
                "message": "Ticket created (simulated)",
            }
        )
    return _TOOL_EXECUTORS["tool_create_ticket"](node, payload, ctx)


@register_executor("tool_send_whatsapp")
def _tool_send_whatsapp(node, payload, ctx):
    if ctx.get("$sandbox"):
        config = node.get("config", {}) or {}
        phone = config.get("phone") or payload.get("phone", "unknown")
        return _sandbox_result(
            f"Send WhatsApp message to {phone}",
            {
                "message_id": "sandbox-wa-msg-001",
                "phone": phone,
                "message": "WhatsApp message sent (simulated)",
            }
        )
    return _TOOL_EXECUTORS["tool_send_whatsapp"](node, payload, ctx)


@register_executor("tool_send_whatsapp_template")
def _tool_send_whatsapp_template(node: dict, payload: Any, ctx: dict):
    config = node.get("config", {}) or {}
    mapping = config.get("mapping", {}) or {}

    template_cfg = config.get("template") or {}
    template_id = (
        config.get("template_id")
        or template_cfg.get("id")
        or template_cfg.get("name")
    )

    if not template_id:
        error = "WhatsApp template not configured"
        _record_tool_failure(ctx, node, payload, error)
        return {"success": False, "error": error}

    atomic = config.get("atomic_options", {}) or {}
    save_contact = atomic.get("save_contact", False)
    notify_agent = atomic.get("notify_agent", False)
    contact_type_id = atomic.get("contact_type_id")
    flow_context = atomic.get("flow_context") or config.get("flow_context")

    # ----------------------------
    # Mapping resolution
    # ----------------------------

    def resolve(expr: Any):
        if isinstance(expr, str) and "{{" in expr and "}}" in expr:
            expr = expr.strip()[2:-2].strip()
            val = _lookup_mapping_path(payload, ctx, expr)
            if val is not None:
                return val
            return _resolve_template(expr, payload, ctx)
        return _resolve_mapping_entry(expr, payload, ctx)

    # ----------------------------
    # Phone (MANDATORY)
    # ----------------------------

    phone_entry = (
            mapping.get("phone_number")
            or mapping.get("phone")
            or mapping.get("whatsapp_number")
    )

    if not phone_entry:
        error = "Missing phone mapping (expected PHONE_NUMBER)"
        _record_tool_failure(ctx, node, payload, error)
        return {"success": False, "error": error}

    # ✅ unwrap mapping entry
    phone_expr = (
        phone_entry.get("value")
        if isinstance(phone_entry, dict)
        else phone_entry
    )

    phone = resolve(phone_expr)
    if not phone:
        error = "Could not resolve whatsapp_number from mapping"
        if isinstance(phone_expr, str) and "input." in phone_expr and "input.body." not in phone_expr:
            error = (
                "Could not resolve whatsapp_number from mapping. "
                "This flow is using the new runtime contract: use 'input.body.<field>' instead of 'input.<field>'."
            )
        _record_tool_failure(ctx, node, payload, error)
        return {"success": False, "error": error}

    # ----------------------------
    # Build VALUES for Celery task
    # ----------------------------

    values = {
        "whatsapp_number": str(phone)
    }

    for key, expr in mapping.items():
        if key in ("phone_number", "PHONE_NUMBER", "phone", "whatsapp_number"):
            continue
        value = resolve(expr)
        if value is None:
            error = f"Template parameter '{key}' could not be resolved"
            if isinstance(expr, str) and "input." in expr and "input.body." not in expr:
                error = (
                    f"Template parameter '{key}' could not be resolved. "
                    "This flow is using the new runtime contract: use 'input.body.<field>' instead of 'input.<field>'."
                )
            _record_tool_failure(ctx, node, payload, error)
            return {"success": False, "error": error}
        values[key] = value

    # ----------------------------
    # Sandbox mode check
    # ----------------------------
    
    if ctx.get("$sandbox"):
        return _sandbox_result(
            f"Send WhatsApp template '{template_id}' to {phone}",
            {
                "template_id": template_id,
                "phone": phone,
                "values": values,
                "sent_count": 1,
                "failed_count": 0,
                "results": [{"index": 0, "success": True, "message_id": "sandbox-wa-001", "phone": phone}],
            }
        )

    # ----------------------------
    # Execute synchronously
    # ----------------------------

    try:
        result = send_whatsapp_template(
            tenant_id=ctx.get("tenant_id"),
            template_id=template_id,
            values=values,
            save_contact=save_contact,
            contact_type_id=contact_type_id,
            notify_agent=notify_agent,
            flow_context=flow_context,
            flow_execution_id=ctx.get("execution_id"),
        )
        return result
    except Exception as e:
        _record_tool_failure(ctx, node, payload, str(e))
        return {"success": False, "error": str(e)}



@register_executor("tool_send_email")
def _tool_send_email(node, payload, ctx):
    if ctx.get("$sandbox"):
        config = node.get("config", {}) or {}
        email = config.get("email") or config.get("to") or payload.get("email", "unknown")
        subject = config.get("subject") or payload.get("subject", "No Subject")
        return _sandbox_result(
            f"Send email to {email}: {subject}",
            {
                "message_id": "sandbox-email-001",
                "recipient": email,
                "subject": subject,
                "message": "Email sent (simulated)",
            }
        )
    return _TOOL_EXECUTORS["tool_send_email"](node, payload, ctx)


@register_executor("tool_http_request")
def _tool_http_request(node, payload, ctx):
    if ctx.get("$sandbox"):
        config = node.get("config", {}) or {}
        url = config.get("url") or payload.get("url", "unknown")
        method = config.get("method", "GET")
        return _sandbox_result(
            f"HTTP {method} request to {url}",
            {
                "status_code": 200,
                "response_data": {"sandbox": True, "message": "Simulated response"},
                "response_headers": {"X-Sandbox": "true"},
                "url": url,
                "method": method,
            }
        )
    return _TOOL_EXECUTORS["tool_http_request"](node, payload, ctx)


@register_executor("tool_update_candidate")
def _tool_update_candidate(node, payload, ctx):
    if ctx.get("$sandbox"):
        config = node.get("config", {}) or {}
        candidate_id = config.get("candidate_id") or payload.get("candidate_id", "unknown")
        status = config.get("status") or payload.get("status", "updated")
        return _sandbox_result(
            f"Update candidate {candidate_id} to status: {status}",
            {
                "candidate_id": candidate_id,
                "status": status,
                "message": "Candidate updated (simulated)",
            }
        )
    return _TOOL_EXECUTORS["tool_update_candidate"](node, payload, ctx)


@register_executor("tool_crm_crud")
def _tool_crm_crud(node: dict, payload: Any, ctx: dict) -> dict:
    from flows.core.executors.crm_crud import execute_crm_crud
    return execute_crm_crud(node, payload, ctx)


# ---------------------------------------------------------------------
#  OUTPUTS
# ---------------------------------------------------------------------


def _append_output(ctx, kind, node, payload):
    """Accumulate outputs during preview."""

    ctx.setdefault("$outputs", []).append({
        "kind": kind,
        "node": node.get("name"),
        "payload": payload,
    })
    return {"dispatched": kind, "payload": payload}


@register_executor("output_function")
def _out_func(node, payload, ctx):
    """Dispatch to a Python function handler."""

    return _append_output(ctx, "function", node, payload)


@register_executor("delay")
def _exec_delay(node, payload, ctx):
    """Pause execution for a number of seconds before continuing."""

    config = node.get("config", {}) or {}
    seconds = config.get("seconds")
    if seconds is None:
        seconds = (payload or {}).get("seconds", 0)
    try:
        seconds = float(seconds)
    except Exception:
        return {"success": False, "error": "seconds must be a number"}

    # Clamp to reasonable limits
    seconds = max(0.0, min(seconds, 86400.0))

    if seconds > 0:
        time.sleep(seconds)

    _append_output(ctx, "delay", node, payload)
    return {"success": True, "seconds": seconds, "payload": payload}


@register_executor("flow_script")
def _exec_flow_script(node, payload, ctx):
    """Execute a stored Flow Script (optionally a specific version)."""

    config = node.get("config", {}) or {}
    tenant_id = ctx.get("tenant_id")
    script_id = config.get("script_id") or (payload or {}).get("script_id")
    version_id = config.get("version_id") or (payload or {}).get("version_id")
    input_payload = config.get("input_payload")
    if input_payload is None:
        input_payload = payload or {}

    def _render_deep(value):
        if isinstance(value, dict):
            return {k: _render_deep(v) for k, v in value.items()}
        if isinstance(value, list):
            return [_render_deep(v) for v in value]
        if isinstance(value, str):
            # Allow {{input.body.*}}, {{nodes.<id>.output.*}}, {{config.*}}, {{ctx.*}}
            #
            # Important: if the value is a single placeholder (e.g. "{{nodes.x.output.schema}}"),
            # return the resolved object (dict/list/primitive) instead of a string coercion.
            if _is_single_placeholder_string(value):
                return _resolve_template(value, payload, ctx)
            return render_template_string(value, payload, ctx)
        return value

    try:
        input_payload = _render_deep(input_payload)
    except Exception as exc:
        return {"success": False, "error": f"Failed to render input_payload templates: {exc}"}

    # Resolve $datalab_resultset references so the script receives schema/preview in params
    if tenant_id and isinstance(input_payload, dict):
        input_payload = resolve_datalab_param_refs(input_payload, str(tenant_id))

    if not tenant_id:
        return {"success": False, "error": "Missing tenant_id in context"}
    if not script_id:
        return {"success": False, "error": "script_id is required"}

    try:
        script = FlowScript.objects.get(id=script_id, tenant_id=tenant_id)
    except FlowScript.DoesNotExist:
        return {"success": False, "error": f"FlowScript {script_id} not found"}

    if version_id:
        version = script.versions.filter(id=version_id).first()
        if version is None:
            return {"success": False, "error": "Version not found for this script"}
    else:
        version = script.published_version or script.latest_version
        if version is None:
            return {"success": False, "error": "No version available to run"}

    run = FlowScriptRun.objects.create(
        tenant=script.tenant,
        flow=script.flow,
        script=script,
        version=version,
        input_payload=input_payload,
        status=FlowScriptRun.STATUS_PENDING,
    )

    FlowScriptLog.objects.create(
        run=run,
        tenant=script.tenant,
        level=FlowScriptLog.LEVEL_INFO,
        message="Run queued.",
    )

    execute_script_run.apply_async(
        args=[str(run.id)],
        queue=FLOWS_Q,
    )

    return {
        "success": True,
        "run_id": str(run.id),
        "script_id": str(script.id),
        "version_id": str(version.id),
        "status": "queued",
    }


@register_executor("output_task")
def _out_task(node, payload, ctx):
    """Dispatch to a Celery task."""

    return _append_output(ctx, "task", node, payload)


@register_executor("output_event")
def _out_event(node, payload, ctx):
    """Emit an event to the event system."""
    from uuid import UUID
    
    config = node.get("config", {})
    event_name = config.get("event_name", "")
    
    if not event_name:
        return {"success": False, "error": "No event_name configured"}
    
    tenant_id = ctx.get("tenant_id")
    if not tenant_id:
        return {"success": False, "error": "No tenant_id in context"}
    
    event_payload = payload
    payload_template = config.get("payload_template")
    if payload_template and payload_template != "{}":
        try:
            import json
            scope = {"payload": payload, "ctx": ctx, "context": ctx}
            event_payload = eval(f"f'''{payload_template}'''", {"__builtins__": _SAFE_BUILTINS}, scope)
            if isinstance(event_payload, str):
                event_payload = json.loads(event_payload)
        except Exception:
            pass
    
    try:
        from moio_platform.core.events.emitter import emit_event
        from central_hub.models import Tenant
        
        entity_type = event_name.split(".")[0] if "." in event_name else "flow"
        entity_id = ctx.get("entity_id") or ctx.get("$input", {}).get("id")
        
        system_actor_id = UUID("00000000-0000-0000-0000-000000000001")

        # Events are keyed by Tenant.tenant_code (UUID) in EventLog.
        tenant_code = ctx.get("tenant_code")
        if not tenant_code:
            try:
                tenant = Tenant.objects.get(id=tenant_id)
                tenant_code = tenant.tenant_code
            except Exception:
                tenant_code = None

        if not tenant_code:
            return {"success": False, "error": "Could not resolve tenant_code for event emission"}

        emit_event(
            name=event_name,
            tenant_id=UUID(str(tenant_code)),
            actor={"type": "system", "id": str(system_actor_id)},
            entity={"type": entity_type, "id": str(entity_id) if entity_id else None},
            payload=event_payload if isinstance(event_payload, dict) else {"data": event_payload},
            source="flow_output",
        )
        
        _append_output(ctx, "event", node, {"event_name": event_name, "payload": event_payload})
        return {"success": True, "event_name": event_name, "payload": event_payload}
        
    except Exception as e:
        logger.warning(f"Failed to emit event {event_name}: {e}")
        _append_output(ctx, "event", node, {"event_name": event_name, "error": str(e)})
        return {"success": False, "error": str(e)}


@register_executor("datalab_file_adapter")
def _exec_datalab_file_adapter(node, payload, ctx):
    """
    Execute a Data Lab ImportProcess (File Adapter) and return a ResultSet.
    """
    config = node.get("config", {}) or {}
    tenant_id = ctx.get("tenant_id")
    import_process_id = config.get("import_process_id")
    source = config.get("source") or (payload or {}).get("source") or {}
    materialize = bool(config.get("materialize", False))
    
    if not tenant_id:
        return {"success": False, "error": "Missing tenant_id in context"}
    if not import_process_id:
        return {"success": False, "error": "import_process_id is required"}
    if not isinstance(source, dict) or not source:
        return {"success": False, "error": "source is required (file_id or fileset_id)"}
    
    try:
        import_process = ImportProcess.objects.get(id=import_process_id, tenant_id=tenant_id)
    except ImportProcess.DoesNotExist:
        return {"success": False, "error": f"ImportProcess {import_process_id} not found"}
    
    executor = ImportExecutor()
    try:
        resultset = executor.execute(
            source=source,
            contract_json=import_process.contract_json,
            materialize=materialize,
            user=None,
        )
        return {
            "success": True,
            "resultset_id": str(resultset.id),
            "row_count": resultset.row_count,
            "schema": resultset.schema_json,
        }
    except Exception as exc:
        logger.error(f"datalab_file_adapter failed: {exc}", exc_info=True)
        return {"success": False, "error": str(exc)}


@register_executor("datalab_promote")
def _exec_datalab_promote(node, payload, ctx):
    """
    Promote a ResultSet to a Dataset (create new or new version).
    """
    config = node.get("config", {}) or {}
    tenant_id = ctx.get("tenant_id")
    resultset_id = config.get("resultset_id") or (payload or {}).get("resultset_id")
    dataset_id = config.get("dataset_id")
    dataset_name = config.get("dataset_name")
    mode = (config.get("mode") or "new_version").lower()
    description = config.get("description") or ""
    
    if not tenant_id:
        return {"success": False, "error": "Missing tenant_id in context"}
    if not resultset_id:
        return {"success": False, "error": "resultset_id is required"}
    
    try:
        resultset = ResultSet.objects.get(id=resultset_id, tenant_id=tenant_id)
    except ResultSet.DoesNotExist:
        return {"success": False, "error": f"ResultSet {resultset_id} not found"}
    
    # Resolve or create dataset
    if dataset_id:
        try:
            dataset = Dataset.objects.get(id=dataset_id, tenant_id=tenant_id)
        except Dataset.DoesNotExist:
            return {"success": False, "error": f"Dataset {dataset_id} not found"}
    else:
        if not dataset_name:
            return {"success": False, "error": "dataset_name is required when creating a new dataset"}
        dataset = Dataset.objects.create(
            tenant_id=tenant_id,
            name=dataset_name,
            description=description,
        )
    
    # Determine version_number
    version_number = 1
    if getattr(dataset, "current_version", None) and mode in {"new_version", "append", "replace"}:
        version_number = dataset.current_version.version_number + 1
    
    new_version = DatasetVersion.objects.create(
        tenant_id=tenant_id,
        dataset=dataset,
        version_number=version_number,
        description=description,
        is_current=True,
        result_set=resultset,
    )
    
    # Update current pointer
    DatasetVersion.objects.filter(dataset=dataset, is_current=True).exclude(id=new_version.id).update(is_current=False)
    dataset.current_version = new_version
    dataset.save(update_fields=["current_version", "updated_at"])
    
    if not resultset.dataset_version_id:
        resultset.dataset_version = new_version
        resultset.save(update_fields=["dataset_version"])
    
    return {
        "success": True,
        "dataset_id": str(dataset.id),
        "version_number": new_version.version_number,
        "row_count": resultset.row_count,
    }


@register_executor("datalab_ingest")
def _exec_datalab_ingest(node, payload, ctx):
    """
    Ingest a file into Data Lab: pass-through by file_id, or create FileAsset from url or content_base64.
    Returns file_id, filename, content_type, size, storage_key.
    """
    from django.core.files.base import ContentFile
    from django.core.files.storage import default_storage
    import uuid as uuid_lib
    import base64 as b64
    from urllib.request import urlopen
    from urllib.error import URLError, HTTPError

    config = node.get("config", {}) or {}
    incoming = (config or {}) if not (payload or {}) else {**(config or {}), **(payload or {})}
    tenant_id = ctx.get("tenant_id")

    if not tenant_id:
        return {"success": False, "error": "Missing tenant_id in context"}

    file_id = incoming.get("file_id")
    url = incoming.get("url")
    content_base64 = incoming.get("content_base64")
    filename = incoming.get("filename") or "upload.bin"
    content_type = (incoming.get("content_type") or "application/octet-stream").strip() or "application/octet-stream"

    # Pass-through: already have a Data Lab file_id
    if file_id:
        try:
            asset = FileAsset.objects.get(id=file_id, tenant_id=tenant_id)
        except FileAsset.DoesNotExist:
            return {"success": False, "error": f"FileAsset {file_id} not found"}
        return {
            "success": True,
            "file_id": str(asset.id),
            "filename": asset.filename,
            "content_type": asset.content_type,
            "size": asset.size,
            "storage_key": asset.storage_key,
        }

    # Create from URL
    if url:
        try:
            safe_url = _validate_datalab_ingest_url(url)
        except ValueError as e:
            return {"success": False, "error": f"Invalid URL: {e}"}
        try:
            with urlopen(safe_url, timeout=30) as resp:
                raw = resp.read()
                suggested = filename
                if suggested == "upload.bin" and getattr(resp, "headers", None):
                    cd = resp.headers.get("Content-Disposition")
                    if cd and "filename=" in cd:
                        suggested = cd.split("filename=")[-1].strip('"\' \n').split(";")[0].strip()
                filename = suggested or "download.bin"
        except (URLError, HTTPError, OSError) as e:
            logger.warning(f"datalab_ingest url open failed: {e}")
            return {"success": False, "error": f"Failed to download URL: {e}"}
        if len(raw) > 100 * 1024 * 1024:
            return {"success": False, "error": "Download exceeds 100MB limit"}
        storage_key = f"datalab/files/{tenant_id}/{uuid_lib.uuid4().hex}_{filename}"
        try:
            actual_key = default_storage.save(storage_key, ContentFile(raw))
        except Exception as e:
            logger.error(f"datalab_ingest save failed: {e}", exc_info=True)
            return {"success": False, "error": f"Failed to save file: {e}"}
        asset = FileAsset.objects.create(
            tenant_id=tenant_id,
            storage_key=actual_key,
            filename=filename,
            content_type=content_type,
            size=len(raw),
            uploaded_by=None,
            metadata={},
        )
        return {
            "success": True,
            "file_id": str(asset.id),
            "filename": asset.filename,
            "content_type": asset.content_type,
            "size": asset.size,
            "storage_key": asset.storage_key,
        }

    # Create from inline base64
    if content_base64:
        try:
            raw = b64.b64decode(content_base64)
        except Exception as e:
            return {"success": False, "error": f"Invalid base64 content: {e}"}
        if len(raw) > 100 * 1024 * 1024:
            return {"success": False, "error": "Content exceeds 100MB limit"}
        storage_key = f"datalab/files/{tenant_id}/{uuid_lib.uuid4().hex}_{filename}"
        try:
            actual_key = default_storage.save(storage_key, ContentFile(raw, name=filename))
        except Exception as e:
            logger.error(f"datalab_ingest save failed: {e}", exc_info=True)
            return {"success": False, "error": f"Failed to save file: {e}"}
        asset = FileAsset.objects.create(
            tenant_id=tenant_id,
            storage_key=actual_key,
            filename=filename,
            content_type=content_type,
            size=len(raw),
            uploaded_by=None,
            metadata={},
        )
        return {
            "success": True,
            "file_id": str(asset.id),
            "filename": asset.filename,
            "content_type": asset.content_type,
            "size": asset.size,
            "storage_key": asset.storage_key,
        }

    return {"success": False, "error": "One of file_id, url, or content_base64 is required"}


@register_executor("datalab_resultset_get")
def _exec_datalab_resultset_get(node, payload, ctx):
    """
    Fetch ResultSet metadata and optional preview by id (tenant-scoped; works for ephemeral ResultSets).
    """
    config = node.get("config", {}) or {}
    tenant_id = ctx.get("tenant_id")
    resultset_id = config.get("resultset_id") or (payload or {}).get("resultset_id")
    include_preview = config.get("include_preview", True)
    preview_limit = max(0, min(1000, int(config.get("preview_limit") or 200)))

    if not tenant_id:
        return {"success": False, "error": "Missing tenant_id in context"}
    if not resultset_id:
        return {"success": False, "error": "resultset_id is required"}

    try:
        resultset = ResultSet.objects.get(id=resultset_id, tenant_id=tenant_id)
    except ResultSet.DoesNotExist:
        return {"success": False, "error": f"ResultSet {resultset_id} not found"}

    preview_json = []
    if include_preview and resultset.preview_json:
        preview_json = list(resultset.preview_json)[:preview_limit]

    return {
        "success": True,
        "resultset_id": str(resultset.id),
        "schema_json": resultset.schema_json or {},
        "row_count": resultset.row_count,
        "is_json_object": getattr(resultset, "is_json_object", False),
        "preview_json": preview_json,
        "storage": resultset.storage,
        "storage_key": resultset.storage_key or None,
        "origin": resultset.origin,
    }


@register_executor("output_webhook_reply")
def _out_webhook(node, payload, ctx):
    """Send webhook response."""

    return _append_output(ctx, "webhook_reply", node, payload)


@register_executor("output_agent")
def _out_agent(node, payload, ctx):
    """Dispatch to an AI Agent."""

    return _append_output(ctx, "agent", node, payload)


# ---------------------------------------------------------------------
#  AGENT PROCESSING
# ---------------------------------------------------------------------


@register_executor("agent")
def _agent_executor(node, payload, ctx):
    """Execute an AI agent node using the OpenAI Agent SDK.
    
    Supports two modes:
    1. Pre-built agent: If config.use_configured_agent is True, uses build_agents_for_tenant()
       for proper hydration with tenant tool customizations and handoffs.
    2. Flow-defined agent: Creates agent from flow config with optional overrides.
    
    Integrates with FlowAgentContext for shared context across multiple agent invocations.
    """

    from .agent_runtime import FlowAgentRuntime, FlowAgentConfig
    from .context_service import FlowAgentContextService
    from central_hub.models import Tenant

    config = node.get("config", {})
    tenant_id = ctx.get("tenant_id")
    node_id = node.get("id", "")
    flow_execution_id = ctx.get("flow_execution_id")
    use_flow_session = bool(config.get("use_flow_session", True))

    if not tenant_id:
        return {"success": False, "error": "No tenant_id in context"}

    try:
        tenant = Tenant.objects.get(id=tenant_id)
    except Tenant.DoesNotExist:
        return {"success": False, "error": f"Tenant {tenant_id} not found"}

    # Get or create agent context for this flow execution (shared session).
    agent_context = None
    agent_turn = None
    if use_flow_session and flow_execution_id:
        try:
            from flows.models import FlowExecution
            flow_execution = FlowExecution.objects.get(id=flow_execution_id)
            agent_context, _ = FlowAgentContextService.get_or_create_context(flow_execution, tenant)
        except Exception as e:
            logger.warning(f"Could not get/create agent context: {e}")

    # Determine agent to run (design-time configured AgentConfiguration).
    agent_id = (config or {}).get("agent_id")
    if not agent_id:
        return {"success": False, "error": "Missing agent_id in node config"}
    
    try:
        from chatbot.models.agent_configuration import AgentConfiguration
        try:
            agent_cfg_db = AgentConfiguration.objects.get(id=agent_id, tenant=tenant, enabled=True)
        except AgentConfiguration.DoesNotExist:
            return {"success": False, "error": f"AgentConfiguration {agent_id} not found or disabled"}

        if not agent_cfg_db.name:
            return {"success": False, "error": f"AgentConfiguration {agent_id} is missing a name"}

        # Use pre-built agent from tenant configuration for proper hydration (tools, handoffs, customizations).
        from chatbot.agents.moio_agents_loader import build_agents_for_tenant
        tenant_agents = build_agents_for_tenant(tenant)
        agent_name = str(agent_cfg_db.name)

        if agent_name not in tenant_agents:
            return {"success": False, "error": f"Agent '{agent_name}' not loadable for tenant"}

        agent = tenant_agents[agent_name]
            
    except Exception as e:
        return {"success": False, "error": f"Failed to build agent: {str(e)}"}

    # Get conversation history from shared context or ctx (or isolate the run).
    if use_flow_session:
        if agent_context:
            conversation = FlowAgentContextService.get_conversation_history(agent_context)
            # Merge shared variables into ctx
            ctx.update(FlowAgentContextService.get_shared_variables(agent_context))
        else:
            conversation = ctx.get("conversation_history", [])
    else:
        conversation = []

    # -----------------------------
    # Prompt input source (strict):
    # - The agent prompt is defined only by config.input_message (rendered).
    # - The execution-time "raw user input" is derived from the trigger input ($input)
    #   and is exposed as ctx.workflow.input_as_text for templates.
    # -----------------------------
    trigger_body = None
    if isinstance(ctx, dict):
        raw_input_container = ctx.get("$input") or {}
        if isinstance(raw_input_container, dict):
            trigger_body = raw_input_container.get("body")
    raw_user_input: str = ""
    if isinstance(trigger_body, dict):
        for key in ("message", "text", "content"):
            val = trigger_body.get(key)
            if isinstance(val, str) and val.strip():
                raw_user_input = val
                break
    if not raw_user_input:
        if isinstance(payload, dict):
            val = payload.get("message")
            if isinstance(val, str):
                raw_user_input = val

    # Seed workflow.* in the real ctx (stable, allowed in ctx_schema); do not override if already set.
    workflow = ctx.setdefault("workflow", {}) if isinstance(ctx, dict) else {}
    if isinstance(workflow, dict):
        workflow.setdefault("input_as_text", raw_user_input)
        workflow.setdefault("input", raw_user_input)

    # Ensure we have a template prompt configured; default to the raw user input passthrough.
    input_template = (config.get("input_message") or "").strip()
    if not input_template:
        input_template = "{{ctx.workflow.input_as_text}}"
        if isinstance(config, dict):
            config["input_message"] = input_template

    # Note: we pass raw_user_input as the "message" arg; runtime renders config.input_message into final prompt.
    input_payload = {"message": raw_user_input, "payload": payload}
    
    # NOTE: Do NOT append conversation_history into itself.
    # The runtime will append the message if configured to include chat history.

    # Start agent turn for tracking (only when shared session is enabled).
    if use_flow_session and agent_context:
        try:
            agent_turn = FlowAgentContextService.start_turn(
                agent_context,
                agent_name=agent_name,
                node_id=node_id,
                input_payload=input_payload
            )
        except Exception as e:
            logger.warning(f"Could not start agent turn: {e}")

    if use_flow_session:
        ctx["conversation_history"] = conversation

    try:
        runtime = FlowAgentRuntime(tenant)
        # Build a config object for runtime behavior (input_message, include_chat_history, etc).
        agent_cfg = None
        try:
            # FlowAgentConfig expects `name` to be present; inject from the selected AgentConfiguration.
            runtime_cfg = dict(config or {})
            runtime_cfg["name"] = agent_name
            agent_cfg = FlowAgentConfig.from_dict(runtime_cfg)
        except Exception:
            agent_cfg = None

        # IMPORTANT: _run_agent expects a string `message`, not the conversation list.
        # Passing the list creates circular references and triggers RecursionError.
        #
        # Provide a runner_context copy so we can attach helpful session/contact/config values
        # without polluting the stable flow ctx contract.
        agent_ctx = dict(ctx) if isinstance(ctx, dict) else {}
        if not use_flow_session:
            agent_ctx.pop("conversation_history", None)
        # Tools in moio_agent_tools_repo often expect ctx.context["session"], ["contact"], ["config"].
        # Provide lightweight, dot-accessible wrappers here (runner context only).
        from flows.core.lib import DotAccessDict
        from central_hub.tenant_config import get_tenant_config

        # Tenant configuration (used by multiple tools for API keys / catalog ids / tenant pointer).
        try:
            agent_ctx.setdefault("config", get_tenant_config(tenant))
        except Exception:
            # Don't hard-fail agent runs if tenant config lookup fails.
            pass

        # Session-like object (minimum fields commonly used by tools).
        session_obj = DotAccessDict({
            "tenant_id": str(tenant.id),
            "channel": (trigger_body or {}).get("channel") if isinstance(trigger_body, dict) else None,
            "flow_execution_id": str(flow_execution_id) if flow_execution_id else None,
            "agent_context_id": str(getattr(agent_context, "id", None)) if agent_context else None,
            "session": str(flow_execution_id) if flow_execution_id else None,
        })
        agent_ctx.setdefault("session", session_obj)

        # Contact-like object (best-effort, from internal contract if present).
        if isinstance(ctx, dict) and "contact" in ctx and "contact" not in agent_ctx:
            contact_val = ctx.get("contact")
            if isinstance(contact_val, dict):
                agent_ctx["contact"] = DotAccessDict(contact_val)
            else:
                agent_ctx["contact"] = contact_val

        agent_ctx.setdefault("agent_config", dict(config or {}))

        # Check if human mode is enabled on the AgentSession - skip AI response generation but still handle incoming message
        human_mode_enabled = False
        session_id = ctx.get("session_id")
        if not session_id and isinstance(trigger_body, dict):
            session_id = trigger_body.get("session_id")
        if not session_id and flow_execution_id:
            try:
                from flows.models import FlowExecution

                flow_execution_record = FlowExecution.objects.only("input_data").get(
                    id=flow_execution_id
                )
                input_data = (
                    flow_execution_record.input_data
                    if isinstance(flow_execution_record.input_data, dict)
                    else {}
                )
                session_id = input_data.get("session_id")
            except Exception:
                pass
        if session_id:
            try:
                from chatbot.models import AgentSession
                session = AgentSession.objects.get(pk=session_id, tenant=tenant)
                human_mode_enabled = session.human_mode
            except Exception:
                # Session not found or error - continue with normal flow
                pass

        if human_mode_enabled:
            # Human mode: process incoming message and store in conversation history, but skip AI response
            if use_flow_session:
                ctx["conversation_history"] = conversation

            # Add user message to conversation history if configured
            if not config or config.get("include_chat_history", True):
                input_role = config.get("input_role", "user") if config else "user"
                conversation.append({
                    "role": input_role,
                    "content": raw_user_input or ""
                })

                # Update context with new conversation history
                if agent_ctx:
                    agent_ctx["conversation_history"] = conversation

            # Return response indicating human mode was used
            node_output = {
                "success": True,
                "agent": agent_name,
                "turn_id": str(agent_turn.id) if agent_turn else None,
                "output": {"human_mode": True, "message_processed": True},
                "response": None,  # No AI response generated
                "messages": [{"role": "user", "content": raw_user_input or ""}],
                "tool_calls": [],
                "human_mode": True
            }

            # Make agent output visible in preview outputs panel
            _append_output(ctx, "agent", node, node_output)

            # Complete turn with human mode results
            if agent_turn:
                try:
                    FlowAgentContextService.complete_turn(
                        agent_turn,
                        output_payload=node_output,
                        tool_calls=[],
                        messages=node_output["messages"],
                        merge_variables={"agent_output": node_output},
                    )
                except Exception as e:
                    logger.warning(f"Could not complete agent turn: {e}")

            return node_output

        # Run with the raw trigger/user input. The runtime will render config.input_message into final prompt.
        result = runtime._run_agent(agent, raw_user_input or "", context=agent_ctx, config=agent_cfg)
        
        # Extract output and messages from result
        from flows.core.agent_runtime import _normalise_output

        output_payload = {}
        messages = []
        tool_calls = []
        
        if hasattr(result, "final_output"):
            output_payload = {"output": _normalise_output(result.final_output)}
        if hasattr(result, "new_items"):
            for item in result.new_items:
                if hasattr(item, "role") and hasattr(item, "content"):
                    messages.append({"role": item.role, "content": item.content})
                if hasattr(item, "tool_calls"):
                    for tc in item.tool_calls:
                        tool_calls.append({
                            "name": getattr(tc, "name", "unknown"),
                            "args": getattr(tc, "arguments", {}),
                        })

        # Normalize the node output so it is always JSON-safe and useful for downstream placeholders.
        normalized_output = output_payload.get("output")
        response_text = normalized_output if isinstance(normalized_output, str) else None
        if response_text is None and isinstance(normalized_output, dict):
            # Common conventions for structured outputs.
            response_text = (
                normalized_output.get("response")
                or normalized_output.get("message")
                or normalized_output.get("text")
            )
            if response_text is not None and not isinstance(response_text, str):
                response_text = str(response_text)
        if response_text in (None, "") and messages:
            # Fallback when the SDK produced assistant messages but no final_output.
            # Pick the last assistant content.
            for msg in reversed(messages):
                if msg.get("role") == "assistant" and msg.get("content") not in (None, ""):
                    response_text = str(msg.get("content"))
                    break

        node_output = {
            "success": True,
            "agent": agent_name,
            "turn_id": str(agent_turn.id) if agent_turn else None,
            "output": normalized_output,
            "response": response_text,
            "messages": messages,
            "tool_calls": tool_calls,
        }

        # Make agent output visible in preview outputs panel.
        _append_output(ctx, "agent", node, node_output)
        
        # Complete turn with results
        if agent_turn:
            try:
                FlowAgentContextService.complete_turn(
                    agent_turn,
                    output_payload=node_output,
                    tool_calls=tool_calls,
                    messages=messages,
                    merge_variables={"agent_output": node_output},
                )
            except Exception as e:
                logger.warning(f"Could not complete agent turn: {e}")
        
    except Exception as e:
        # Mark turn as failed
        if agent_turn:
            try:
                FlowAgentContextService.fail_turn(agent_turn, str(e))
            except Exception:
                pass
        return {"success": False, "error": f"Agent execution failed: {str(e)}"}

    return node_output


__all__ = [
    "PortSpec",
    "PortMap",
    "NodeDefinition",
    "NodeRegistry",
    "registry",
    "register_node",
    "register_executor",
    "get_executor",
    "default_executor",
]

