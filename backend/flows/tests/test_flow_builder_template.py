import json
from uuid import uuid4
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.db import connection
from django.db.models.signals import post_save
from django.http import HttpResponse
from django.test import Client, RequestFactory, TestCase
from django.urls import reverse

from crm.models import WebhookConfig
from flows.models import Flow, FlowGraphVersion
from flows.views import flow_builder, flow_builder_react, whatsapp_templates
from flows.registry import palette_by_category
from flows.core.registry import NodeDefinition, registry as runtime_registry
from portal.models import MoioUser, Tenant, TenantConfiguration
from portal.signals import create_internal_contact


class FlowBuilderTemplateTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.factory = RequestFactory()
        post_save.disconnect(create_internal_contact, sender=get_user_model())
        self.addCleanup(
            lambda: post_save.connect(create_internal_contact, sender=get_user_model())
        )
        self.tenant = Tenant.objects.create(
            nombre="Acme Corp",
            enabled=True,
            domain="acme.test",
        )
        config, _ = TenantConfiguration.objects.get_or_create(tenant=self.tenant)
        config.whatsapp_name = f"test-{uuid4()}"
        config.whatsapp_integration_enabled = True
        config.save()
        self.user = MoioUser.objects.create_user(
            email="user@example.com",
            username="user",
            password="secret",
            tenant=self.tenant,
        )
        self.flow = Flow.objects.create(
            tenant=self.tenant,
            name="Sample Flow",
            description="",
            status="testing",
            is_enabled=False,
            created_by=self.user,
        )
        FlowGraphVersion.objects.create(
            flow=self.flow,
            major=1,
            minor=0,
            is_published=False,
            graph={"nodes": [], "edges": [], "meta": {}},
        )

    def test_legacy_builder_redirects_to_react(self):
        request = self.factory.get(
            reverse("flows:builder_legacy_redirect", args=[self.flow.id]),
            HTTP_HX_REQUEST="true",
        )
        request.user = self.user

        response = flow_builder(request, self.flow.id)
        self.assertEqual(response.status_code, 204)
        self.assertIn("HX-Redirect", response.headers)
        self.assertIn(
            reverse("flows:builder_react", args=[self.flow.id]),
            response.headers.get("HX-Redirect", ""),
        )

    def test_react_builder_template_renders(self):
        request = self.factory.get(
            reverse("flows:builder_react", args=[self.flow.id]),
            HTTP_HX_REQUEST="true",
        )
        request.user = self.user

        with patch("flows.views.WebhookConfig", None), patch(
            "flows.views.render"
        ) as mock_render:
            mock_render.return_value = HttpResponse(status=200)
            response = flow_builder_react(request, self.flow.id)

        self.assertEqual(response.status_code, 200)

        _, template_name, context = mock_render.mock_calls[0].args
        self.assertEqual(template_name, "flows/flow_builder_react.html")
        self.assertIn("graph", context)
        self.assertIn("node_definitions", context)

    def test_palette_respects_stage_metadata(self):
        kind = "test_flow_builder_stage"
        definition = NodeDefinition(
            kind=kind,
            title="Stage gated",
            icon="beaker",
            category="Testing",
            stages={"dev": True, "prod": False},
        )
        runtime_registry.register(definition)
        self.addCleanup(lambda: runtime_registry._definitions.pop(kind, None))

        url = reverse("flows:builder_react", args=[self.flow.id])

        request_prod = self.factory.get(url, HTTP_HX_REQUEST="true")
        request_prod.user = self.user
        with patch("flows.views.WebhookConfig", None), patch(
            "flows.views.render"
        ) as mock_render_prod, self.settings(DEBUG=False):
            mock_render_prod.return_value = HttpResponse(status=200)
            flow_builder_react(request_prod, self.flow.id)

        _, _, context_prod = mock_render_prod.mock_calls[0].args
        self.assertEqual(context_prod["builder_stage"], "prod")
        self.assertFalse(
            any(
                node.kind == kind
                for category in context_prod["palette"]
                for node in category["items"]
            )
        )

        request_dev = self.factory.get(f"{url}?stage=dev", HTTP_HX_REQUEST="true")
        request_dev.user = self.user
        with patch("flows.views.WebhookConfig", None), patch(
            "flows.views.render"
        ) as mock_render_dev, self.settings(DEBUG=False):
            mock_render_dev.return_value = HttpResponse(status=200)
            flow_builder_react(request_dev, self.flow.id)

        _, _, context_dev = mock_render_dev.mock_calls[0].args
        self.assertEqual(context_dev["builder_stage"], "dev")
        self.assertTrue(
            any(
                node.kind == kind
                for category in context_dev["palette"]
                for node in category["items"]
            )
        )

    def test_flow_builder_filters_available_webhooks(self):
        if WebhookConfig is None:
            self.skipTest("WebhookConfig model not available")

        if WebhookConfig._meta.db_table not in connection.introspection.table_names():
            self.skipTest("WebhookConfig table not created in test database")

        other_flow = Flow.objects.create(
            tenant=self.tenant,
            name="Other Flow",
            description="",
            status="testing",
            is_enabled=False,
            created_by=self.user,
        )

        other_tenant = Tenant.objects.create(
            nombre="Beta Corp",
            enabled=True,
            domain="beta.test",
        )

        matching = WebhookConfig.objects.create(
            tenant=self.tenant,
            name="Flow Handler",
            description=f"flow:{self.flow.id}",
            handler_path="flows.handlers.execute_flow_webhook",
        )
        shared = WebhookConfig.objects.create(
            tenant=self.tenant,
            name="Shared Handler",
            description="",
            handler_path="flows.handlers.execute_flow_webhook",
        )
        WebhookConfig.objects.create(
            tenant=self.tenant,
            name="Other Flow Handler",
            description=f"flow:{other_flow.id}",
            handler_path="flows.handlers.execute_flow_webhook",
        )
        WebhookConfig.objects.create(
            tenant=self.tenant,
            name="Wrong Handler",
            description="",
            handler_path="crm.handlers.process",
        )
        WebhookConfig.objects.create(
            tenant=other_tenant,
            name="Foreign Handler",
            description=f"flow:{self.flow.id}",
            handler_path="flows.handlers.execute_flow_webhook",
        )

        request = self.factory.get(
            reverse("flows:builder_react", args=[self.flow.id]),
            HTTP_HX_REQUEST="true",
        )
        request.user = self.user

        with patch("flows.views.render") as mock_render:
            mock_render.return_value = HttpResponse(status=200)
            flow_builder_react(request, self.flow.id)

        _, _, context = mock_render.mock_calls[0].args
        available = context["available_webhooks"]

        self.assertEqual({entry["name"] for entry in available}, {matching.name, shared.name})
        self.assertTrue(
            all(
                entry["handler_path"] == "flows.handlers.execute_flow_webhook"
                for entry in available
            )
        )
        self.assertTrue(all(isinstance(entry["id"], str) for entry in available))

    @patch("chatbot.lib.whatsapp_client_api.template_requirements")
    @patch("chatbot.lib.whatsapp_client_api.WhatsappBusinessClient")
    def test_whatsapp_templates_view_returns_placeholders(
        self, mock_client, mock_requirements
    ):
        mock_client.return_value.download_message_templates.return_value = [
            {
                "id": "tmpl-1",
                "name": "welcome",
                "language": "en_US",
                "category": "MARKETING",
                "status": "APPROVED",
                "components": [{"type": "BODY", "text": "Hi {{name}}"}],
            }
        ]
        mock_requirements.return_value = [
            {"type": "body", "parameters": [{"type": "text", "parameter_name": "name"}]}
        ]

        request = self.factory.get(
            reverse("flows:whatsapp_templates", args=[self.flow.id]),
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        request.user = self.user

        response = whatsapp_templates(request, self.flow.id)

        self.assertEqual(response.status_code, 200)
        payload = json.loads(response.content.decode("utf-8"))
        self.assertIn("templates", payload)
        self.assertEqual(len(payload["templates"]), 1)
        template = payload["templates"][0]
        self.assertEqual(template["id"], "tmpl-1")
        self.assertEqual(template["name"], "welcome")
        self.assertEqual(template["language"], "en_US")
        placeholders = template.get("placeholders")
        self.assertTrue(placeholders)
        keys = {entry["key"] for entry in placeholders}
        self.assertIn("body_name", keys)
