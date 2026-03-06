from flows.registry import REGISTRY, serialize_definitions, palette_by_category
from flows.core.registry import (
    NodeDefinition,
    get_executor,
    registry as runtime_registry,
)


def test_ui_and_runtime_share_single_registry_instance():
    assert REGISTRY is runtime_registry

    agent_ui = REGISTRY["agent"]
    agent_runtime = runtime_registry["agent"]

    assert agent_ui is agent_runtime
    assert get_executor("agent") is agent_ui.executor


def test_branch_ports_reflect_rules_and_else_flag():
    definition = REGISTRY["logic_branch"]

    ports = definition.compute_ports({"rules": [{"name": "foo"}], "else": True})
    out_names = [port.name for port in ports["out"]]

    assert out_names == ["foo", "else"]


def test_while_ports_provide_yes_no_branches():
    definition = REGISTRY["logic_while"]

    ports = definition.compute_ports({})
    out_names = [port.name for port in ports["out"]]

    assert out_names == ["yes", "no"]


def test_agent_ports_include_schema_metadata():
    definition = REGISTRY["agent"]

    ports = definition.serialize_ports(definition.default_config)
    agent_in = ports["in"][0]
    agent_out = ports["out"][0]

    assert agent_in["schema"]["properties"]["message"]["type"] == "string"
    assert "schema_preview" in agent_out and agent_out["schema_preview"]


def test_serialize_definitions_merges_metadata_and_ports():
    definitions = serialize_definitions()

    assert "agent" in definitions
    agent = definitions["agent"]

    assert agent["default_config"]["model"] == "gpt-4.1-mini"
    assert agent["ports"]["out"][0]["schema"]["properties"]["response"]["type"] == "string"


def test_serialized_node_includes_stage_metadata_and_availability():
    kind = "test_stage_node"
    definition = NodeDefinition(
        kind=kind,
        title="Stage Node",
        icon="beaker",
        category="Testing",
        stages={"dev": True, "prod": False},
    )
    runtime_registry.register(definition)

    try:
        definitions = serialize_definitions(stage="prod")
        assert kind in definitions
        payload = definitions[kind]

        assert payload["stages"] == {"dev": True, "prod": False}
        assert payload["availability"] == {"dev": True, "prod": False}
        assert payload["stage_limited"] is True
        assert payload["is_available"] is False
        assert payload["ports"]["meta"]["stages"] == {"dev": True, "prod": False}
    finally:
        runtime_registry._definitions.pop(kind, None)


def test_palette_filters_nodes_by_stage_flags():
    kind = "test_stage_palette"
    definition = NodeDefinition(
        kind=kind,
        title="Palette Stage Node",
        icon="bug",
        category="Testing",
        availability={"dev": True, "prod": False},
    )
    runtime_registry.register(definition)

    try:
        dev_palette = palette_by_category(stage="dev")
        prod_palette = palette_by_category(stage="prod")

        dev_kinds = {node.kind for nodes in dev_palette.values() for node in nodes}
        prod_kinds = {node.kind for nodes in prod_palette.values() for node in nodes}

        assert kind in dev_kinds
        assert kind not in prod_kinds
    finally:
        runtime_registry._definitions.pop(kind, None)
