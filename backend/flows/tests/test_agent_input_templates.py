import uuid

import pytest

from flows.core.agent_runtime import FlowAgentConfig, FlowAgentExecutionError, FlowAgentRuntime
from flows.core.registry import get_executor


def test_agent_input_message_renders_ctx_placeholders(tenant, monkeypatch):
    from flows.core import agent_runtime as agent_runtime_module

    captured = {}

    async def stub_run(*, starting_agent, input, context):
        captured["input"] = input
        captured["context"] = context

        class Result:
            final_output = "ok"
            new_items = []

        return Result()

    monkeypatch.setattr(agent_runtime_module.Runner, "run", stub_run)

    runtime = FlowAgentRuntime(tenant)
    dummy_agent = type("DummyAgent", (), {"name": "agent"})()

    cfg = FlowAgentConfig(
        name="agent",
        input_message="Hello {{ctx.user.name}} / {{ctx.workflow.input_as_text}}",
        include_chat_history=True,
        input_role="user",
    )
    ctx = {"user": {"name": "Alice"}, "conversation_history": []}

    runtime._run_agent(dummy_agent, "RAW", context=ctx, config=cfg)

    assert captured["input"][-1]["role"] == "user"
    assert captured["input"][-1]["content"] == "Hello Alice / RAW"


def test_agent_input_message_template_missing_key_raises(tenant, monkeypatch):
    from flows.core import agent_runtime as agent_runtime_module

    async def stub_run(*, starting_agent, input, context):
        class Result:
            final_output = "ok"
            new_items = []

        return Result()

    monkeypatch.setattr(agent_runtime_module.Runner, "run", stub_run)

    runtime = FlowAgentRuntime(tenant)
    dummy_agent = type("DummyAgent", (), {"name": "agent"})()

    cfg = FlowAgentConfig(
        name="agent",
        input_message="Hello {{ctx.user.missing}}",
        include_chat_history=True,
        input_role="user",
    )
    ctx = {"user": {}, "conversation_history": []}

    with pytest.raises(FlowAgentExecutionError):
        runtime._run_agent(dummy_agent, "RAW", context=ctx, config=cfg)


def test_agent_executor_isolated_session_does_not_touch_flow_session(tenant, monkeypatch):
    from flows.core import agent_runtime as agent_runtime_module
    from flows.core import context_service as context_service_module

    # If this is called while use_flow_session=False, the test should fail.
    def _boom(*args, **kwargs):
        raise AssertionError("FlowAgentContextService.get_or_create_context should not be called")

    monkeypatch.setattr(
        context_service_module.FlowAgentContextService,
        "get_or_create_context",
        staticmethod(_boom),
    )

    dummy_agent = type("DummyAgent", (), {"name": "agent"})()
    captured = {}

    def stub_run_agent(self, agent, message, context, config=None):
        captured["context"] = context

        class Result:
            final_output = "ok"
            new_items = []

        return Result()

    monkeypatch.setattr(agent_runtime_module.FlowAgentRuntime, "_run_agent", stub_run_agent)

    executor = get_executor("agent")
    node = {
        "id": "node-agent",
        "kind": "agent",
        "name": "Agent",
        "config": {
            "agent_id": str(uuid.uuid4()),
            "use_flow_session": False,
            "input_message": "{{ctx.workflow.input_as_text}}",
        },
    }
    ctx = {
        "tenant_id": tenant.id,
        "flow_execution_id": uuid.uuid4(),
        "conversation_history": [{"role": "user", "content": "prev"}],
        "foo": "bar",
        "$input": {"body": {"message": "from-trigger"}},
    }
    payload = {"message": "hi"}

    # Patch AgentConfiguration lookup in executor: we only need a name for loader selection.
    from chatbot.models.agent_configuration import AgentConfiguration

    class _FakeCfg:
        id = uuid.uuid4()
        name = "Agent"
        enabled = True

    monkeypatch.setattr(AgentConfiguration.objects, "get", lambda *args, **kwargs: _FakeCfg())

    from chatbot.agents import moio_agents_loader
    monkeypatch.setattr(moio_agents_loader, "build_agents_for_tenant", lambda _tenant: {"Agent": dummy_agent})

    result = executor(node, payload, ctx)

    assert result["success"] is True
    # Isolated mode should not mutate the flow ctx, but it must not reuse or append to history.
    assert ctx["conversation_history"] == [{"role": "user", "content": "prev"}]
    assert captured["context"] is not ctx
    assert "conversation_history" not in captured["context"]


def test_agent_executor_prefers_trigger_input_for_workflow_input(tenant, monkeypatch):
    """Ensure ctx.workflow.input_as_text is seeded from ctx.$input.body.* (not from payload stringification)."""
    from flows.core import agent_runtime as agent_runtime_module
    from flows.core import context_service as context_service_module

    # Avoid session context calls (we don't need DB models here).
    monkeypatch.setattr(
        context_service_module.FlowAgentContextService,
        "get_or_create_context",
        staticmethod(lambda *args, **kwargs: (None, False)),
    )

    dummy_agent = type("DummyAgent", (), {"name": "agent"})()

    def stub_build_agent(self, config):
        return dummy_agent

    captured = {}

    def stub_run_agent(self, agent, message, context, config=None):
        captured["message"] = message
        captured["context"] = context

        class Result:
            final_output = "ok"
            new_items = []

        return Result()

    monkeypatch.setattr(agent_runtime_module.FlowAgentRuntime, "_build_agent", stub_build_agent)
    monkeypatch.setattr(agent_runtime_module.FlowAgentRuntime, "_run_agent", stub_run_agent)

    executor = get_executor("agent")
    node = {
        "id": "node-agent",
        "kind": "agent",
        "name": "Agent",
        "config": {
            "agent_id": str(uuid.uuid4()),
            "input_message": "{{ctx.workflow.input_as_text}}",
            "use_flow_session": False,
        },
    }
    ctx = {
        "tenant_id": tenant.id,
        "$input": {"body": {"message": "from-trigger"}},
    }
    payload = {"not_message": {"huge": "object"}}

    # Patch AgentConfiguration lookup in executor: we only need a name for loader selection.
    from chatbot.models.agent_configuration import AgentConfiguration

    class _FakeCfg:
        id = uuid.uuid4()
        name = "Agent"
        enabled = True

    monkeypatch.setattr(AgentConfiguration.objects, "get", lambda *args, **kwargs: _FakeCfg())

    from chatbot.agents import moio_agents_loader
    monkeypatch.setattr(moio_agents_loader, "build_agents_for_tenant", lambda _tenant: {"Agent": dummy_agent})

    result = executor(node, payload, ctx)
    assert result["success"] is True

    # The raw message passed into runtime should come from trigger input.
    assert captured["message"] == "from-trigger"
    # workflow.* should be seeded in flow ctx for templates.
    assert ctx["workflow"]["input_as_text"] == "from-trigger"
    # Runner context should include session + agent_config helpers.
    assert isinstance(captured["context"].get("session"), dict)
    assert isinstance(captured["context"].get("agent_config"), dict)


