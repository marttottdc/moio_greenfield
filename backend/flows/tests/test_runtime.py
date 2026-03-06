from django.test import SimpleTestCase

from flows.core.registry import register_executor, register_node
from flows.core.runtime import FlowRun, FlowRunError
from flows.core.lib import render_template_string


TEST_INCREMENT_KIND = "runtime_test_increment"


try:  # Ensure the helper node is available once per test run
    register_node(
        kind=TEST_INCREMENT_KIND,
        title="Runtime Increment",
        icon="test",
        category="Tests",
    )
except Exception:  # pragma: no cover - already registered
    pass


@register_executor(TEST_INCREMENT_KIND)
def _runtime_test_increment(node, payload, ctx):
    data = dict(payload or {})
    # Support both flat and nested payload shapes.
    if "loop" in data and isinstance(data.get("loop"), dict):
        loop = dict(data.get("loop") or {})
        loop["count"] = int(loop.get("count", 0)) + 1
        data["loop"] = loop
        # Mirror into ctx contract (must already exist via Normalize).
        ctx.setdefault("loop", {})
        if isinstance(ctx.get("loop"), dict):
            ctx["loop"]["count"] = loop["count"]
        return data

    data["count"] = int(data.get("count", 0)) + 1
    ctx["count"] = data["count"]
    return data


class FlowRunTests(SimpleTestCase):
    def test_straight_line_flow_records_steps(self):
        graph = {
            "nodes": [
                {
                    "id": "t1",
                    "kind": "trigger_manual",
                    "name": "Trigger",
                    "ports": {"out": [{"name": "out"}]},
                },
                {
                    "id": "o1",
                    "kind": "output_function",
                    "name": "Output",
                    "ports": {"in": [{"name": "in"}]},
                },
            ],
            "edges": [
                {
                    "id": "e1",
                    "source": "t1",
                    "target": "o1",
                    "source_port": "out",
                    "target_port": "in",
                }
            ],
        }

        payload = {"foo": "bar"}
        run = FlowRun(
            graph,
            payload,
            config={"company": "Moio"},
            tenant_id="tenant-123",
            trigger={"source": "manual"},
        )
        result = run.execute()

        self.assertEqual(result["status"], "success")
        self.assertIn("nodes", result["context"])
        self.assertIn("t1", result["context"]["nodes"])
        self.assertIn("o1", result["context"]["nodes"])
        self.assertEqual(result["context"]["$input"], {"body": payload})
        self.assertEqual(result["context"]["config"], {"company": "Moio"})
        self.assertEqual(result["context"]["tenant_id"], "tenant-123")
        self.assertEqual(result["context"]["$trigger"]["source"], "manual")
        self.assertEqual(len(result["steps"]), 2)
        self.assertTrue(all(step["status"] == "success" for step in result["steps"]))
        self.assertEqual(result["outputs"][0]["kind"], "function")

    def test_template_rendering_supports_config_namespace(self):
        ctx = {"$input": {"body": {}}, "nodes": {}, "config": {"foo": "bar"}}
        rendered = render_template_string("Hello {{ config.foo }}", payload={}, context=ctx)
        self.assertEqual(rendered, "Hello bar")

    def test_template_rendering_supports_ctx_namespace(self):
        ctx = {
            "$input": {"body": {}},
            "nodes": {},
            "config": {"foo": "bar"},
            "event": {"name": "Bob"},
        }
        rendered = render_template_string("Hello {{ ctx.event.name }}", payload={}, context=ctx)
        self.assertEqual(rendered, "Hello Bob")

        # ctx hides runtime/system namespaces like config.
        with self.assertRaises(ValueError):
            render_template_string("Hello {{ ctx.config.foo }}", payload={}, context=ctx)

    def test_branch_flow_selects_correct_port(self):
        graph = {
            "nodes": [
                {
                    "id": "t1",
                    "kind": "trigger_manual",
                    "name": "Trigger",
                    "ports": {"out": [{"name": "out"}]},
                },
                {
                    "id": "n1",
                    "kind": "logic_normalize",
                    "name": "Normalize",
                    "config": {
                        "mappings": [
                            {
                                "ctx_path": "ctx.event.value",
                                "source_path": "input.body.value",
                                "type": "number",
                                "required": True,
                            }
                        ]
                    },
                    "ports": {"in": [{"name": "in"}], "out": [{"name": "out"}]},
                },
                {
                    "id": "b1",
                    "kind": "logic_branch",
                    "name": "Branch",
                    "config": {
                        "rules": [
                            {
                                "name": "gt",
                                "expr": "ctx.event.value > 3",
                            }
                        ],
                        "else": True,
                    },
                    "ports": {
                        "in": [{"name": "in"}],
                        "out": [
                            {"name": "gt"},
                            {"name": "else"},
                        ],
                    },
                },
                {
                    "id": "o_true",
                    "kind": "output_function",
                    "name": "True Output",
                    "ports": {"in": [{"name": "in"}]},
                },
                {
                    "id": "o_false",
                    "kind": "output_task",
                    "name": "False Output",
                    "ports": {"in": [{"name": "in"}]},
                },
            ],
            "edges": [
                {
                    "id": "e1",
                    "source": "t1",
                    "target": "n1",
                    "source_port": "out",
                    "target_port": "in",
                },
                {
                    "id": "e1b",
                    "source": "n1",
                    "target": "b1",
                    "source_port": "out",
                    "target_port": "in",
                },
                {
                    "id": "e2",
                    "source": "b1",
                    "target": "o_true",
                    "source_port": "gt",
                    "target_port": "in",
                },
                {
                    "id": "e3",
                    "source": "b1",
                    "target": "o_false",
                    "source_port": "else",
                    "target_port": "in",
                },
            ],
        }

        run = FlowRun(graph, {"value": 5})
        result = run.execute()

        branch_step = next(step for step in result["steps"] if step["node_id"] == "b1")
        self.assertEqual(branch_step["meta"]["selected_port"], "gt")
        self.assertTrue(all(t["target"] != "o_false" for t in branch_step["transitions"]))
        self.assertIn("nodes", result["context"])
        self.assertIn("o_true", result["context"]["nodes"])
        self.assertNotIn("o_false", result["context"]["nodes"])

    def test_branch_expression_forbidden_input_is_loud(self):
        graph = {
            "nodes": [
                {
                    "id": "t1",
                    "kind": "trigger_manual",
                    "name": "Trigger",
                    "ports": {"out": [{"name": "out"}]},
                },
                {
                    "id": "b1",
                    "kind": "logic_branch",
                    "name": "Branch",
                    "config": {
                        "rules": [
                            {
                                "name": "match",
                                "expr": "input.body.user.name == 'x'",
                            }
                        ],
                        "else": True,
                    },
                    "ports": {
                        "in": [{"name": "in"}],
                        "out": [{"name": "match"}, {"name": "else"}],
                    },
                },
                {
                    "id": "o_match",
                    "kind": "output_function",
                    "name": "Match Output",
                    "ports": {"in": [{"name": "in"}]},
                },
                {
                    "id": "o_else",
                    "kind": "output_task",
                    "name": "Else Output",
                    "ports": {"in": [{"name": "in"}]},
                },
            ],
            "edges": [
                {
                    "id": "e1",
                    "source": "t1",
                    "target": "b1",
                    "source_port": "out",
                    "target_port": "in",
                },
                {
                    "id": "e2",
                    "source": "b1",
                    "target": "o_match",
                    "source_port": "match",
                    "target_port": "in",
                },
                {
                    "id": "e3",
                    "source": "b1",
                    "target": "o_else",
                    "source_port": "else",
                    "target_port": "in",
                },
            ],
        }

        # No `user` key in the initial payload -> strict dot access should raise.
        run = FlowRun(graph, {"mensaje": "aviso"})
        with self.assertRaises(FlowRunError):
            run.execute()

    def test_missing_body_contract_crashes(self):
        graph = {
            "nodes": [
                {"id": "t1", "kind": "trigger_manual", "ports": {"out": [{"name": "out"}]}},
            ],
            "edges": [],
        }
        run = FlowRun(graph, {"mensaje": "aviso"})
        run.context["$input"] = {"mensaje": "aviso"}  # violates contract (missing body)
        with self.assertRaises(FlowRunError):
            run.execute()

    def test_condition_blocks_downstream_when_false(self):
        graph = {
            "nodes": [
                {
                    "id": "t1",
                    "kind": "trigger_manual",
                    "ports": {"out": [{"name": "out"}]},
                },
                {
                    "id": "n1",
                    "kind": "logic_normalize",
                    "config": {
                        "mappings": [
                            {
                                "ctx_path": "ctx.event.run",
                                "source_path": "input.body.run",
                                "type": "boolean",
                                "required": False,
                                "default": False,
                            }
                        ]
                    },
                    "ports": {"in": [{"name": "in"}], "out": [{"name": "out"}]},
                },
                {
                    "id": "c1",
                    "kind": "logic_condition",
                    "config": {"expr": "ctx.event.run == True"},
                    "ports": {"in": [{"name": "in"}], "out": [{"name": "out"}]},
                },
                {
                    "id": "o1",
                    "kind": "output_function",
                    "ports": {"in": [{"name": "in"}]},
                },
            ],
            "edges": [
                {
                    "id": "e1",
                    "source": "t1",
                    "target": "n1",
                    "source_port": "out",
                    "target_port": "in",
                },
                {
                    "id": "e2",
                    "source": "n1",
                    "target": "c1",
                    "source_port": "out",
                    "target_port": "in",
                },
                {
                    "id": "e3",
                    "source": "c1",
                    "target": "o1",
                    "source_port": "out",
                    "target_port": "in",
                },
            ],
        }

        run = FlowRun(graph, {"run": False})
        result = run.execute()

        condition_step = next(step for step in result["steps"] if step["node_id"] == "c1")
        self.assertFalse(condition_step["meta"]["result"])
        self.assertNotIn("o1", result["context"]["nodes"])

    def test_while_loop_accumulates_iterations(self):
        graph = {
            "nodes": [
                {
                    "id": "t1",
                    "kind": "trigger_manual",
                    "ports": {"out": [{"name": "out"}]},
                },
                {
                    "id": "n1",
                    "kind": "logic_normalize",
                    "config": {
                        "mappings": [
                            {
                                "ctx_path": "ctx.loop.count",
                                "source_path": "input.body.count",
                                "type": "integer",
                                "required": True,
                            }
                        ]
                    },
                    "ports": {"in": [{"name": "in"}], "out": [{"name": "out"}]},
                },
                {
                    "id": "w1",
                    "kind": "logic_while",
                    "config": {"expr": "ctx.loop.count < 3"},
                    "ports": {
                        "in": [{"name": "in"}],
                        "out": [
                            {"name": "yes"},
                            {"name": "no"},
                        ],
                    },
                },
                {
                    "id": "inc",
                    "kind": TEST_INCREMENT_KIND,
                    "ports": {"in": [{"name": "in"}], "out": [{"name": "out"}]},
                },
                {
                    "id": "out",
                    "kind": "output_function",
                    "ports": {"in": [{"name": "in"}]},
                },
            ],
            "edges": [
                {
                    "id": "e1",
                    "source": "t1",
                    "target": "n1",
                    "source_port": "out",
                    "target_port": "in",
                },
                {
                    "id": "e2",
                    "source": "n1",
                    "target": "w1",
                    "source_port": "out",
                    "target_port": "in",
                },
                {
                    "id": "e3",
                    "source": "w1",
                    "target": "inc",
                    "source_port": "yes",
                    "target_port": "in",
                },
                {
                    "id": "e4",
                    "source": "w1",
                    "target": "out",
                    "source_port": "no",
                    "target_port": "in",
                },
            ],
        }

        run = FlowRun(graph, {"count": 0})
        result = run.execute()

        loop_step = next(step for step in result["steps"] if step["node_id"] == "w1")
        self.assertEqual(loop_step["meta"]["iterations"], 3)
        self.assertEqual(result["context"]["$loops"]["w1"], 3)
        self.assertEqual(result["context"]["nodes"]["out"]["output"]["payload"]["loop"]["count"], 3)

    def test_runtime_reports_expression_errors(self):
        graph = {
            "nodes": [
                {
                    "id": "t1",
                    "kind": "trigger_manual",
                    "ports": {"out": [{"name": "out"}]},
                },
                {
                    "id": "n1",
                    "kind": "logic_normalize",
                    "config": {
                        "mappings": [
                            {
                                "ctx_path": "ctx.event.value",
                                "source_path": "input.body.value",
                                "type": "number",
                                "required": False,
                            }
                        ]
                    },
                    "ports": {"in": [{"name": "in"}], "out": [{"name": "out"}]},
                },
                {
                    "id": "b1",
                    "kind": "logic_branch",
                    "config": {
                        "rules": [
                            {"name": "fail", "expr": "ctx.event.missing > 0"}
                        ]
                    },
                    "ports": {
                        "in": [{"name": "in"}],
                        "out": [{"name": "fail"}],
                    },
                },
            ],
            "edges": [
                {
                    "id": "e1",
                    "source": "t1",
                    "target": "n1",
                    "source_port": "out",
                    "target_port": "in",
                },
                {
                    "id": "e2",
                    "source": "n1",
                    "target": "b1",
                    "source_port": "out",
                    "target_port": "in",
                },
            ],
        }

        run = FlowRun(graph, {"value": 1})
        with self.assertRaises(FlowRunError):
            run.execute()

        snapshot = run.snapshot()
        self.assertEqual(snapshot["status"], "failed")
        self.assertTrue(any(error["node_id"] == "b1" for error in snapshot["errors"]))
        branch_step = next(step for step in snapshot["steps"] if step["node_id"] == "b1")
        self.assertEqual(branch_step["status"], "error")

    def test_formula_node_supports_payload_dot_access_and_blank_defaults(self):
        graph = {
            "nodes": [
                {
                    "id": "t1",
                    "kind": "trigger_manual",
                    "name": "Trigger",
                    "ports": {"out": [{"name": "out"}]},
                },
                {
                    "id": "f1",
                    "kind": "data_formula",
                    "name": "Formula",
                    "config": {
                        "merge_with_input": True,
                        "formulas": [
                            {
                                "key": "factura_safe",
                                "expr": "coalesce(trim(payload.factura), '-')",
                            },
                            {
                                "key": "nested_name",
                                "expr": "payload.user.name",
                            },
                        ],
                    },
                    "ports": {"in": [{"name": "in"}], "out": [{"name": "out"}]},
                },
                {
                    "id": "o1",
                    "kind": "output_function",
                    "name": "Output",
                    "ports": {"in": [{"name": "in"}]},
                },
            ],
            "edges": [
                {"id": "e1", "source": "t1", "target": "f1", "source_port": "out", "target_port": "in"},
                {"id": "e2", "source": "f1", "target": "o1", "source_port": "out", "target_port": "in"},
            ],
        }

        run = FlowRun(graph, {"factura": "", "user": {"name": "Bob"}})
        result = run.execute()

        self.assertEqual(result["status"], "success")
        formula_out = result["context"]["nodes"]["f1"]["output"]
        # merge_with_input=True keeps original keys and adds computed ones.
        self.assertEqual(formula_out["factura"], "")
        self.assertEqual(formula_out["user"]["name"], "Bob")
        # "" should be treated as empty by coalesce(..., "-")
        self.assertEqual(formula_out["factura_safe"], "-")
        # Nested dot access should work (payload.user.name)
        self.assertEqual(formula_out["nested_name"], "Bob")

        run2 = FlowRun(graph, {"factura": "   ", "user": {"name": "Bob"}})
        result2 = run2.execute()
        formula_out2 = result2["context"]["nodes"]["f1"]["output"]
        # trim("   ") => "" so coalesce should still fall back
        self.assertEqual(formula_out2["factura_safe"], "-")
