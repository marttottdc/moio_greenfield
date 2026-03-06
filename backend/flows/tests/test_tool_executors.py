import pytest

from flows.core.registry import get_executor


@pytest.mark.parametrize(
    "kind, helper_name, payload, expected_kwargs",
    [
        (
            "tool_create_contact",
            "create_crm_contact",
            {"name": "Alice", "email": "alice@example.com"},
            {"name": "Alice", "email": "alice@example.com", "tenant_id": "tenant-1"},
        ),
        (
            "tool_create_ticket",
            "create_crm_ticket",
            {"title": "Issue", "description": "Test"},
            {"title": "Issue", "description": "Test", "tenant_id": "tenant-1"},
        ),
        (
            "tool_send_whatsapp",
            "send_whatsapp_message",
            {"phone": "+111", "message": "Hello"},
            {"phone": "+111", "message": "Hello", "tenant_id": "tenant-1"},
        ),
        (
            "tool_send_email",
            "send_email",
            {"to": "bob@example.com", "subject": "Hi", "body": "Hello"},
            {"to": "bob@example.com", "subject": "Hi", "body": "Hello", "tenant_id": "tenant-1"},
        ),
        (
            "tool_http_request",
            "http_request",
            {"url": "https://example.com", "method": "POST", "body": {"foo": "bar"}},
            {"url": "https://example.com", "method": "POST", "body": {"foo": "bar"}},
        ),
        (
            "tool_update_candidate",
            "update_candidate_status",
            {"candidate_id": "cand-1", "status": "hired"},
            {"candidate_id": "cand-1", "status": "hired", "tenant_id": "tenant-1"},
        ),
    ],
)
def test_tool_executors_call_helpers(monkeypatch, kind, helper_name, payload, expected_kwargs):
    from flows.core import platform_tools

    calls = {}

    if helper_name == "http_request":
        def stub(url, method="GET", headers=None, body=None):
            kwargs = {
                "url": url,
                "method": method,
                "headers": headers,
                "body": body,
            }
            calls["kwargs"] = {k: v for k, v in kwargs.items() if v is not None}
            return {"success": True, "helper": helper_name}
    else:
        def stub(**kwargs):
            calls["kwargs"] = kwargs
            return {"success": True, "helper": helper_name}

    monkeypatch.setattr(platform_tools, helper_name, stub)

    node = {"id": "node-1", "kind": kind, "name": "Tool", "config": {}}
    ctx = {"tenant_id": "tenant-1"}

    executor = get_executor(kind)
    result = executor(node, payload, ctx)

    assert result == {"success": True, "helper": helper_name}
    assert calls["kwargs"] == expected_kwargs
    assert "$tool_failures" not in ctx


def test_tool_executor_uses_node_config(monkeypatch):
    from flows.core import platform_tools

    captured = {}

    def stub(**kwargs):
        captured["kwargs"] = kwargs
        return {"success": True}

    monkeypatch.setattr(platform_tools, "send_email", stub)

    node = {
        "id": "node-2",
        "kind": "tool_send_email",
        "name": "Email",
        "config": {"subject": "Static subject", "from_email": "robot@example.com"},
    }
    ctx = {"tenant_id": "tenant-1"}

    payload = {"to": "user@example.com", "subject": "Dynamic"}
    executor = get_executor("tool_send_email")

    executor(node, payload, ctx)

    assert captured["kwargs"] == {
        "to": "user@example.com",
        "subject": "Dynamic",
        "from_email": "robot@example.com",
        "tenant_id": "tenant-1",
    }


def test_tool_send_email_renders_templates_from_event_context(monkeypatch):
    from flows.core import platform_tools

    captured = {}

    def stub(**kwargs):
        captured["kwargs"] = kwargs
        return {"success": True}

    monkeypatch.setattr(platform_tools, "send_email", stub)

    node = {
        "id": "node-email",
        "kind": "tool_send_email",
        "name": "Email",
        "config": {
            "to": "ops@moio.test",
            "subject": "El Deal {{input.body.title}} ha cambiado de etapa",
            "body": "Deal {{input.body.title}}: {{input.body.from_stage_name}} → {{input.body.to_stage_name}}",
        },
    }
    ctx = {
        "tenant_id": "tenant-1",
        "$input": {
            "body": {
                "title": "ACME - Renewal",
                "from_stage_name": "Consulta Whatsapp",
                "to_stage_name": "Chat con Cliente",
            }
        },
    }

    executor = get_executor("tool_send_email")
    executor(node, payload={}, ctx=ctx)

    assert captured["kwargs"]["to"] == "ops@moio.test"
    assert captured["kwargs"]["tenant_id"] == "tenant-1"
    assert captured["kwargs"]["subject"] == "El Deal ACME - Renewal ha cambiado de etapa"
    assert captured["kwargs"]["body"] == "Deal ACME - Renewal: Consulta Whatsapp → Chat con Cliente"


def test_tool_send_email_missing_template_keys_fail_fast(monkeypatch):
    from flows.core import platform_tools

    captured = {}

    def stub(**kwargs):
        captured["kwargs"] = kwargs
        return {"success": True}

    monkeypatch.setattr(platform_tools, "send_email", stub)

    node = {
        "id": "node-email-missing",
        "kind": "tool_send_email",
        "name": "Email",
        "config": {
            "to": "ops@moio.test",
            "subject": "El Deal {{input.body.title}} ha cambiado de etapa",
            "body": "Deal {{input.body.title}}: {{input.body.from_stage_name}} → {{input.body.to_stage_name}}",
        },
    }
    ctx = {
        "tenant_id": "tenant-1",
        "$input": {
            "body": {
                # title intentionally missing (this is the production error case)
                "from_stage_name": "Consulta Whatsapp",
                "to_stage_name": "Chat con Cliente",
            }
        },
    }

    executor = get_executor("tool_send_email")
    with pytest.raises(Exception):
        executor(node, payload={}, ctx=ctx)


def test_tool_send_email_html_body_autoescapes_placeholders(monkeypatch):
    from flows.core import platform_tools

    captured = {}

    def stub(**kwargs):
        captured["kwargs"] = kwargs
        return {"success": True}

    monkeypatch.setattr(platform_tools, "send_email", stub)

    node = {
        "id": "node-email-html",
        "kind": "tool_send_email",
        "name": "Email",
        "config": {
            "to": "ops@moio.test",
            "subject": "HTML test",
            "body": "<div>Deal: <strong>{{ input.body.title }}</strong></div>",
        },
    }
    ctx = {
        "tenant_id": "tenant-1",
        "$input": {"body": {"title": 'ACME & <b>Co</b>'}},
    }

    executor = get_executor("tool_send_email")
    executor(node, payload={}, ctx=ctx)

    # Only the placeholder output should be escaped; the surrounding HTML is kept.
    assert captured["kwargs"]["body"] == "<div>Deal: <strong>ACME &amp; &lt;b&gt;Co&lt;/b&gt;</strong></div>"


def test_tool_send_email_rejects_non_path_expressions(monkeypatch):
    from flows.core import platform_tools

    captured = {}

    def stub(**kwargs):
        captured["kwargs"] = kwargs
        return {"success": True}

    monkeypatch.setattr(platform_tools, "send_email", stub)

    node = {
        "id": "node-email-html-safe",
        "kind": "tool_send_email",
        "name": "Email",
        "config": {
            "to": "ops@moio.test",
            "subject": "HTML safe test",
            "body": "<div>{{ safe('<b>OK</b>') }}</div>",
        },
    }
    ctx = {"tenant_id": "tenant-1", "$input": {"body": {}}}

    executor = get_executor("tool_send_email")
    with pytest.raises(Exception):
        executor(node, payload={}, ctx=ctx)


def test_tool_executor_records_failure(monkeypatch):
    from flows.core import platform_tools

    def stub(**kwargs):
        return {"success": False, "error": "boom"}

    monkeypatch.setattr(platform_tools, "send_email", stub)

    node = {"id": "node-3", "kind": "tool_send_email", "name": "Email", "config": {}}
    payload = {"to": "user@example.com", "subject": "Hi", "body": "Hello"}
    ctx = {"tenant_id": "tenant-1"}

    executor = get_executor("tool_send_email")
    result = executor(node, payload, ctx)

    assert result == {"success": False, "error": "boom"}
    assert "$tool_failures" in ctx
    failure = ctx["$tool_failures"][0]
    assert failure["node_name"] == "Email"
    assert failure["kind"] == "tool_send_email"
    assert failure["error"] == "boom"


def test_tool_executor_converts_exceptions(monkeypatch):
    from flows.core import platform_tools

    def stub(**kwargs):
        raise RuntimeError("network down")

    monkeypatch.setattr(platform_tools, "send_email", stub)

    node = {"id": "node-4", "kind": "tool_send_email", "name": "Email", "config": {}}
    payload = {"to": "user@example.com", "subject": "Hi", "body": "Hello"}
    ctx = {"tenant_id": "tenant-1"}

    executor = get_executor("tool_send_email")
    result = executor(node, payload, ctx)

    assert result["success"] is False
    assert "network down" in result["error"]
    assert "$tool_failures" in ctx
    failure = ctx["$tool_failures"][0]
    assert failure["error"] == "network down"


