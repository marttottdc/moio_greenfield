import uuid

from django.test import TestCase

from flows.core.registry import get_executor
from flows.models import Flow, FlowScript, FlowScriptRun, FlowScriptVersion
from portal.models import Tenant


class FlowScriptExecutorTemplateRoutingTests(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(
            nombre="Script Executor Tenant",
            enabled=True,
            domain=f"script-executor-{uuid.uuid4().hex[:8]}.test",
        )
        self.flow = Flow.objects.create(
            tenant=self.tenant,
            name=f"Flow {uuid.uuid4().hex[:6]}",
            status="active",
        )
        self.script = FlowScript.objects.create(
            tenant=self.tenant,
            flow=self.flow,
            name="Template Script",
            slug=f"template-script-{uuid.uuid4().hex[:8]}",
            description="",
        )
        FlowScriptVersion.objects.create(
            script=self.script,
            tenant=self.tenant,
            flow=self.flow,
            version_number=1,
            code="def main(params):\n    return params",
            requirements="",
            parameters={},
            notes="",
        )

        self.executor = get_executor("flow_script")
        self.enqueued = {}
        from flows.core import registry as registry_module

        self._original_script_task = registry_module.execute_script_run

        class DummyTask:
            def apply_async(_self, *args, **kwargs):
                self.enqueued["args"] = args
                self.enqueued["kwargs"] = kwargs

        registry_module.execute_script_run = DummyTask()
        self.addCleanup(
            lambda: setattr(
                registry_module, "execute_script_run", self._original_script_task
            )
        )

    def _execute(self, *, input_payload, payload, ctx):
        node = {
            "id": "flow-script-node",
            "kind": "flow_script",
            "config": {
                "script_id": str(self.script.id),
                "input_payload": input_payload,
            },
        }
        return self.executor(node, payload, ctx)

    def test_flow_script_executor_renders_multi_placeholder_strings(self):
        payload = {"first": "Ada", "last": "Lovelace"}
        cases = [
            ("{{input.body.first}}{{input.body.last}}", "AdaLovelace"),
            ("{{input.body.first}} {{input.body.last}}", "Ada Lovelace"),
        ]

        for template, expected in cases:
            with self.subTest(template=template):
                ctx = {
                    "tenant_id": self.tenant.id,
                    "$input": {"body": payload},
                    "nodes": {},
                    "config": {},
                }
                result = self._execute(
                    input_payload={"message": template},
                    payload=payload,
                    ctx=ctx,
                )

                self.assertTrue(result["success"], result)
                run = FlowScriptRun.objects.get(id=result["run_id"])
                self.assertEqual(run.input_payload["message"], expected)
                self.assertIn("queue", self.enqueued.get("kwargs", {}))

    def test_flow_script_executor_preserves_object_for_single_placeholder(self):
        schema = {"type": "object", "properties": {"name": {"type": "string"}}}
        ctx = {
            "tenant_id": self.tenant.id,
            "$input": {"body": {}},
            "nodes": {"fetch": {"output": {"schema": schema}}},
            "config": {},
        }

        result = self._execute(
            input_payload={"schema": "{{nodes.fetch.output.schema}}"},
            payload={},
            ctx=ctx,
        )

        self.assertTrue(result["success"], result)
        run = FlowScriptRun.objects.get(id=result["run_id"])
        self.assertEqual(run.input_payload["schema"], schema)
