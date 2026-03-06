import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from flows.core.schema import FlowGraph, GraphValidationError, validate_graph_payload
from flows.core.contract import FlowContractError, validate_flow_contract


def test_validate_graph_payload_accepts_valid_graph():
    payload = {
        "nodes": [
            {"id": "start", "kind": "trigger_manual", "ports": {"out": [{"name": "next"}]}},
            {"id": "end", "kind": "output_function", "ports": {"in": [{"name": "in"}]}},
        ],
        "edges": [
            {"id": "edge-1", "source": "start", "target": "end", "source_port": "next", "target_port": "in"}
        ],
        "meta": {"draft": True},
    }

    graph = validate_graph_payload(payload)

    assert isinstance(graph, FlowGraph)
    assert graph.nodes[0].id == "start"
    assert graph.edges[0].source_port == "next"


def test_validate_graph_payload_rejects_duplicate_nodes():
    payload = {
        "nodes": [
            {"id": "dup", "kind": "trigger_manual"},
            {"id": "dup", "kind": "output_function"},
        ],
        "edges": [],
    }

    with pytest.raises(GraphValidationError):
        validate_graph_payload(payload)


def test_validate_graph_payload_rejects_unknown_edge_nodes():
    payload = {
        "nodes": [{"id": "only", "kind": "trigger_manual"}],
        "edges": [{"id": "edge-1", "source": "only", "target": "missing"}],
    }

    with pytest.raises(GraphValidationError):
        validate_graph_payload(payload)


def test_validate_flow_contract_accepts_config_placeholders_and_values():
    graph = {
        "nodes": [
            {"id": "t1", "kind": "trigger_scheduled", "ports": {"out": [{"name": "out"}]}, "config": {}},
            {
                "id": "a1",
                "kind": "agent",
                "ports": {"in": [{"name": "in"}], "out": [{"name": "out"}]},
                "config": {"instructions": "Say: {{ config.greeting }}"},
            },
            {"id": "o1", "kind": "output_function", "ports": {"in": [{"name": "in"}]}, "config": {}},
        ],
        "edges": [
            {"id": "e1", "source": "t1", "target": "a1", "source_port": "out", "target_port": "in"},
            {"id": "e2", "source": "a1", "target": "o1", "source_port": "out", "target_port": "in"},
        ],
    }
    config_schema = {
        "type": "object",
        "properties": {"greeting": {"type": "string"}},
        "required": ["greeting"],
        "additionalProperties": False,
    }
    config_values = {"greeting": "hello"}

    validate_flow_contract(graph, config_schema=config_schema, config_values=config_values)


def test_validate_flow_contract_rejects_missing_config_key_reference():
    graph = {
        "nodes": [
            {"id": "t1", "kind": "trigger_scheduled", "ports": {"out": [{"name": "out"}]}, "config": {}},
            {
                "id": "a1",
                "kind": "agent",
                "ports": {"in": [{"name": "in"}], "out": [{"name": "out"}]},
                "config": {"instructions": "Say: {{ config.missing }}"},
            },
            {"id": "o1", "kind": "output_function", "ports": {"in": [{"name": "in"}]}, "config": {}},
        ],
        "edges": [
            {"id": "e1", "source": "t1", "target": "a1", "source_port": "out", "target_port": "in"},
            {"id": "e2", "source": "a1", "target": "o1", "source_port": "out", "target_port": "in"},
        ],
    }
    config_schema = {
        "type": "object",
        "properties": {"greeting": {"type": "string"}},
        "required": ["greeting"],
        "additionalProperties": False,
    }
    with pytest.raises(FlowContractError):
        validate_flow_contract(graph, config_schema=config_schema, config_values={"greeting": "ok"})


def test_validate_flow_contract_rejects_config_values_type_violation():
    graph = {
        "nodes": [
            {"id": "t1", "kind": "trigger_scheduled", "ports": {"out": [{"name": "out"}]}, "config": {}},
            {
                "id": "a1",
                "kind": "agent",
                "ports": {"in": [{"name": "in"}], "out": [{"name": "out"}]},
                "config": {"instructions": "Say: {{ config.greeting }}"},
            },
            {"id": "o1", "kind": "output_function", "ports": {"in": [{"name": "in"}]}, "config": {}},
        ],
        "edges": [
            {"id": "e1", "source": "t1", "target": "a1", "source_port": "out", "target_port": "in"},
            {"id": "e2", "source": "a1", "target": "o1", "source_port": "out", "target_port": "in"},
        ],
    }
    config_schema = {
        "type": "object",
        "properties": {"greeting": {"type": "string"}},
        "required": ["greeting"],
        "additionalProperties": False,
    }
    with pytest.raises(FlowContractError):
        validate_flow_contract(graph, config_schema=config_schema, config_values={"greeting": 123})


def test_validate_flow_contract_rejects_dynamic_config_values():
    graph = {
        "nodes": [
            {"id": "t1", "kind": "trigger_scheduled", "ports": {"out": [{"name": "out"}]}, "config": {}},
            {
                "id": "a1",
                "kind": "agent",
                "ports": {"in": [{"name": "in"}], "out": [{"name": "out"}]},
                "config": {"instructions": "Say: {{ config.greeting }}"},
            },
            {"id": "o1", "kind": "output_function", "ports": {"in": [{"name": "in"}]}, "config": {}},
        ],
        "edges": [
            {"id": "e1", "source": "t1", "target": "a1", "source_port": "out", "target_port": "in"},
            {"id": "e2", "source": "a1", "target": "o1", "source_port": "out", "target_port": "in"},
        ],
    }
    config_schema = {
        "type": "object",
        "properties": {"greeting": {"type": "string"}},
        "required": ["greeting"],
        "additionalProperties": False,
    }
    with pytest.raises(FlowContractError):
        validate_flow_contract(graph, config_schema=config_schema, config_values={"greeting": "{{ input.body.x }}"})


def test_validate_flow_contract_http_request_accepts_response_schema_for_response_data_paths():
    graph = {
        "nodes": [
            {"id": "t1", "kind": "trigger_scheduled", "ports": {"out": [{"name": "out"}]}, "config": {}},
            {
                "id": "node_2",
                "kind": "tool_http_request",
                "ports": {"in": [{"name": "in"}], "out": [{"name": "out"}]},
                "config": {
                    "url": "https://example.com",
                    # Builder-provided schema IR: this describes the JSON body returned by the API.
                    "output_schema": {
                        "kind": "object",
                        "properties": {
                            "day_of_year": {"kind": "primitive", "type": "number"},
                        },
                    },
                },
            },
            {
                "id": "n3",
                "kind": "logic_normalize",
                "ports": {"in": [{"name": "in"}], "out": [{"name": "out"}]},
                "config": {
                    "mappings": [
                        {
                            "ctx_path": "ctx.doy",
                            "source_path": "nodes.node_2.output.response_data.day_of_year",
                            "type": "string",
                            "required": True,
                            "default": None,
                        }
                    ],
                    "fail_on_missing_required": True,
                },
            },
        ],
        "edges": [
            {"id": "e1", "source": "t1", "target": "node_2", "source_port": "out", "target_port": "in"},
            {"id": "e2", "source": "node_2", "target": "n3", "source_port": "out", "target_port": "in"},
        ],
    }

    validate_flow_contract(graph, config_schema=None, config_values={})


def test_validate_flow_contract_http_request_rejects_flat_response_paths():
    graph = {
        "nodes": [
            {"id": "t1", "kind": "trigger_scheduled", "ports": {"out": [{"name": "out"}]}, "config": {}},
            {
                "id": "node_2",
                "kind": "tool_http_request",
                "ports": {"in": [{"name": "in"}], "out": [{"name": "out"}]},
                "config": {"url": "https://example.com"},
            },
            {
                "id": "n3",
                "kind": "logic_normalize",
                "ports": {"in": [{"name": "in"}], "out": [{"name": "out"}]},
                "config": {
                    "mappings": [
                        {
                            "ctx_path": "ctx.doy",
                            "source_path": "nodes.node_2.output.day_of_year",
                            "type": "string",
                            "required": True,
                            "default": None,
                        }
                    ],
                    "fail_on_missing_required": True,
                },
            },
        ],
        "edges": [
            {"id": "e1", "source": "t1", "target": "node_2", "source_port": "out", "target_port": "in"},
            {"id": "e2", "source": "node_2", "target": "n3", "source_port": "out", "target_port": "in"},
        ],
    }

    with pytest.raises(FlowContractError):
        validate_flow_contract(graph, config_schema=None, config_values={})
