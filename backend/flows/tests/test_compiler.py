from uuid import uuid4

from django.test import TestCase

from flows.core.compiler import FlowCompilationError, compile_flow_graph
from flows.models import Flow, FlowGraphVersion
from central_hub.models import Tenant, TenantConfiguration


class CompilerTests(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(
            nombre="Compiler Tenant",
            enabled=True,
            domain=f"compiler-{uuid4()}@example.com",
        )
        config, _ = TenantConfiguration.objects.get_or_create(tenant=self.tenant)
        config.whatsapp_name = f"compiler-{uuid4()}"
        config.save()

    def _create_flow(self) -> Flow:
        return Flow.objects.create(
            tenant=self.tenant,
            name=f"Flow {uuid4()}",
            description="",
            status="testing",
            is_enabled=False,
        )

    def test_compile_flow_graph_builds_flow_definition(self):
        flow = self._create_flow()
        graph = {
            "nodes": [
                {"id": "t1", "kind": "trigger_manual", "ports": {"out": [{"name": "out"}]}},
                {"id": "o1", "kind": "output_function", "ports": {"in": [{"name": "in"}]}},
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
            "meta": {},
        }
        version = FlowGraphVersion.objects.create(
            flow=flow,
            major=1,
            minor=0,
            is_published=True,
            graph=graph,
        )

        definition = compile_flow_graph(flow, graph, version=version)

        self.assertEqual(definition.flow_id, str(flow.id))
        self.assertEqual(definition.trigger.trigger_type.value, "manual")
        self.assertEqual(definition.trigger.trigger_id, f"manual:{flow.id}")
        self.assertEqual(
            definition.handlers[0].handler_path, "flows.handlers.execute_published_flow"
        )
        self.assertEqual(definition.handlers[0].parameters["flow_id"], str(flow.id))
        self.assertEqual(
            definition.handlers[0].parameters["graph_version_id"], str(version.id)
        )

    def test_compile_flow_graph_requires_trigger(self):
        flow = self._create_flow()
        graph = {
            "nodes": [
                {"id": "o1", "kind": "output_function", "ports": {"in": [{"name": "in"}]}}
            ],
            "edges": [],
        }

        with self.assertRaises(FlowCompilationError):
            compile_flow_graph(flow, graph)

    def test_compile_flow_graph_requires_output(self):
        flow = self._create_flow()
        graph = {
            "nodes": [
                {"id": "t1", "kind": "trigger_manual", "ports": {"out": [{"name": "out"}]}}
            ],
            "edges": [],
        }

        with self.assertRaises(FlowCompilationError):
            compile_flow_graph(flow, graph)
