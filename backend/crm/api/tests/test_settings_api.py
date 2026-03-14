from __future__ import annotations

from crm.api.tests.utils import ensure_schema

ensure_schema()

from django.contrib.auth import get_user_model
from django.db.models.signals import post_save
from django.test.utils import override_settings
from rest_framework import status
from rest_framework.test import APITestCase

from chatbot.models.agent_configuration import AgentConfiguration
from chatbot.models.tenant_tool_configuration import TenantToolConfiguration
from crm.models import WebhookConfig
from central_hub.integrations.models import IntegrationConfig
from central_hub.models import Tenant
from central_hub.signals import create_internal_contact, create_tenant_configurations
from central_hub.tenant_config import get_tenant_config
from central_hub.webhooks.utils import available_handlers
from central_hub.webhooks.registry import webhook_handler


@override_settings(ROOT_URLCONF="crm.api.tests.urls")
class SettingsApiTests(APITestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        post_save.disconnect(create_tenant_configurations, sender=Tenant)
        cls._user_model = get_user_model()
        post_save.disconnect(create_internal_contact, sender=cls._user_model)

    @classmethod
    def tearDownClass(cls):
        post_save.connect(create_internal_contact, sender=cls._user_model)
        post_save.connect(create_tenant_configurations, sender=Tenant)
        super().tearDownClass()

    def setUp(self) -> None:
        self.tenant = Tenant.objects.create(nombre="Tenant A", domain="tenant-a.test")
        self.other_tenant = Tenant.objects.create(nombre="Tenant B", domain="tenant-b.test")

        self.user = self._user_model.objects.create_user(
            email="settings@example.com",
            username="settings-user",
            password="pass1234",
            tenant=self.tenant,
        )
        self.client.force_authenticate(self.user)

        # Seed via IntegrationConfig (replaces TenantConfiguration)
        self.openai_config, _ = IntegrationConfig.objects.get_or_create(
            tenant=self.tenant,
            slug="openai",
            instance_id="default",
            defaults={"config": {}, "enabled": False},
        )
        self.openai_config.config = {"api_key": "tenant-openai", "default_model": "gpt-4o-mini"}
        self.openai_config.save()

        self.whatsapp_config, _ = IntegrationConfig.objects.get_or_create(
            tenant=self.tenant,
            slug="whatsapp",
            instance_id="default",
            defaults={"config": {}, "enabled": False},
        )
        self.whatsapp_config.config = {"name": "tenant-whatsapp"}
        self.whatsapp_config.save()

        IntegrationConfig.objects.get_or_create(
            tenant=self.other_tenant,
            slug="openai",
            instance_id="default",
            defaults={"config": {"api_key": "other-openai"}, "enabled": False},
        )

    def test_openai_settings_are_scoped_to_authenticated_tenant(self) -> None:
        url = "/api/v1/settings/openai/"
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["openai_api_key"], "tenant-openai")
        other_cfg = get_tenant_config(self.other_tenant)
        self.assertNotEqual(response.data["openai_api_key"], other_cfg.openai_api_key)

    def test_partial_update_updates_only_specified_fields(self) -> None:
        url = "/api/v1/settings/openai/"
        payload = {"openai_api_key": "new-secret"}
        response = self.client.patch(url, payload, format="json")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        config = get_tenant_config(self.tenant)
        self.assertEqual(config.openai_api_key, "new-secret")
        self.assertEqual(config.openai_default_model, "gpt-4o-mini")

    def test_agent_crud_respects_tenant_scope(self) -> None:
        other_agent = AgentConfiguration.objects.create(
            tenant=self.other_tenant,
            name="Other",
            model="gpt-4o-mini",
        )

        list_url = "/api/v1/settings/agents/"
        initial = self.client.get(list_url)
        self.assertEqual(initial.status_code, status.HTTP_200_OK)
        self.assertEqual(initial.data, [])

        create_payload = {
            "name": "Support",
            "model": "gpt-4o-mini",
            "instructions": "Assist customers",
            "channel": "whatsapp",
            "channel_id": "123",
            "tools": {"type": "search"},
            "enabled": True,
        }
        created = self.client.post(list_url, create_payload, format="json")
        self.assertEqual(created.status_code, status.HTTP_201_CREATED)
        agent_id = created.data["id"]

        after_create = self.client.get(list_url)
        self.assertEqual(len(after_create.data), 1)

        patch_url = f"{list_url}{agent_id}/"
        patched = self.client.patch(patch_url, {"name": "Support Plus"}, format="json")
        self.assertEqual(patched.status_code, status.HTTP_200_OK)
        self.assertEqual(patched.data["name"], "Support Plus")

        not_found = self.client.get(f"{list_url}{other_agent.id}/")
        self.assertEqual(not_found.status_code, status.HTTP_404_NOT_FOUND)

        deleted = self.client.delete(patch_url)
        self.assertEqual(deleted.status_code, status.HTTP_204_NO_CONTENT)
        final_list = self.client.get(list_url)
        self.assertEqual(final_list.data, [])

    def test_agent_create_accepts_full_payload_with_new_fields(self) -> None:
        """Full payload including handoff_description, guardrails, output, run_behavior is accepted and persisted."""
        list_url = "/api/v1/settings/agents/"
        payload = {
            "name": "Support Triage",
            "handoff_description": "Routes issues to billing/tech/sales agents",
            "instructions": "You triage tickets. Ask minimal questions. Prefer tools.",
            "model": "gpt-5.2",
            "model_settings": {
                "temperature": 0.2,
                "top_p": 1.0,
                "parallel_tool_calls": True,
                "truncation": "auto",
                "max_tokens": 800,
                "verbosity": "low",
                "prompt_cache_retention": "24h",
                "metadata": {"app": "moio"},
            },
            "tools": [
                {"tool_key": "crm.search_contacts", "config": {}},
                {"tool_key": "crm.create_ticket", "config": {"default_priority": "normal"}},
            ],
            "guardrails": {
                "input": [{"guardrail_key": "pii.redact", "config": {}}],
                "output": [{"guardrail_key": "policy.no_secrets", "config": {}}],
            },
            "output": {"mode": "text", "schema": None},
            "run_behavior": {
                "tool_use_behavior": "run_llm_again",
                "reset_tool_choice": True,
            },
        }
        response = self.client.post(list_url, payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["name"], "Support Triage")
        self.assertEqual(response.data["handoff_description"], "Routes issues to billing/tech/sales agents")
        self.assertEqual(response.data["model_settings"]["temperature"], 0.2)
        self.assertEqual(response.data["guardrails"]["input"][0]["guardrail_key"], "pii.redact")
        self.assertEqual(response.data["output"]["mode"], "text")
        self.assertTrue(response.data["run_behavior"]["reset_tool_choice"])

        agent = AgentConfiguration.objects.get(id=response.data["id"])
        self.assertEqual(agent.handoff_description, payload["handoff_description"])
        self.assertEqual(agent.guardrails, payload["guardrails"])
        self.assertEqual(agent.output, payload["output"])
        self.assertEqual(agent.run_behavior, payload["run_behavior"])

    def test_webhook_configuration_validation(self) -> None:
        list_url = "/api/v1/resources/webhooks/"

        invalid_handler_payload = {
            "name": "Invalid Handler",
            "handler_path": "not.registered",
            "auth_type": WebhookConfig.AuthType.BEARER_TOKEN,
            "auth_config": {"token": "secret"},
        }
        invalid_handler = self.client.post(list_url, invalid_handler_payload, format="json")
        self.assertEqual(invalid_handler.status_code, status.HTTP_400_BAD_REQUEST)

        handlers = available_handlers()
        if not handlers:
            @webhook_handler("tests.dummy_webhook")
            def _dummy_handler(*args, **kwargs):  # pragma: no cover - simple registry helper
                return {}

            handlers = available_handlers()

        handler_key = next(iter(handlers))
        missing_auth_payload = {
            "name": "Missing Auth",
            "handler_path": handler_key,
            "auth_type": WebhookConfig.AuthType.BASIC,
            "auth_config": {"username": "user"},
        }
        missing_auth = self.client.post(list_url, missing_auth_payload, format="json")
        self.assertEqual(missing_auth.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("auth_config", missing_auth.data)

        valid_payload = {
            "name": "Valid Hook",
            "description": "Test",
            "handler_path": handler_key,
            "auth_type": WebhookConfig.AuthType.BEARER_TOKEN,
            "auth_config": {"token": "secret"},
        }
        created = self.client.post(list_url, valid_payload, format="json")
        self.assertEqual(created.status_code, status.HTTP_201_CREATED)

        _ = WebhookConfig.objects.create(
            tenant=self.other_tenant,
            name="Other Hook",
            handler_path=handler_key,
        )

        listing = self.client.get(list_url)
        self.assertEqual(listing.status_code, status.HTTP_200_OK)
        self.assertEqual(len(listing.data), 1)
        self.assertEqual(listing.data[0]["name"], "Valid Hook")

    def test_webhook_list_includes_receive_url(self) -> None:
        list_url = "/api/v1/resources/webhooks/"

        handlers = available_handlers()
        if not handlers:
            @webhook_handler("tests.dummy_webhook_url")
            def _dummy_handler(*args, **kwargs):  # pragma: no cover - registry helper
                return {}

            handlers = available_handlers()

        handler_key = next(iter(handlers))

        webhook = WebhookConfig.objects.create(
            tenant=self.tenant,
            name="URL Hook",
            handler_path=handler_key,
        )

        response = self.client.get(list_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(
            response.data[0]["url"], f"http://testserver/webhooks/{webhook.id}/"
        )

    def test_integrations_endpoint_reports_status_and_config(self) -> None:
        self.whatsapp_config.enabled = True
        self.whatsapp_config.config["name"] = "Tenant WhatsApp"
        self.whatsapp_config.save()

        response = self.client.get("/api/v1/settings/integrations/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        integrations = response.data["integrations"]
        whatsapp_entry = next(item for item in integrations if item["id"] == "whatsapp")
        self.assertTrue(whatsapp_entry["connected"])
        self.assertEqual(whatsapp_entry["config"]["whatsapp_name"], "Tenant WhatsApp")

    def test_integration_connect_and_disconnect(self) -> None:
        url = "/api/v1/settings/integrations/openai/connect/"
        payload = {"openai_api_key": "key", "openai_integration_enabled": True}
        connect = self.client.post(url, payload, format="json")
        self.assertEqual(connect.status_code, status.HTTP_200_OK)
        self.assertTrue(connect.data["connected"])

        disconnect = self.client.delete("/api/v1/settings/integrations/openai/")
        self.assertEqual(disconnect.status_code, status.HTTP_200_OK)
        config = get_tenant_config(self.tenant)
        self.assertFalse(config.openai_integration_enabled)

    def test_agent_tools_list_includes_builtins(self) -> None:
        """GET /api/v1/settings/agents/tools/ returns builtin tools (e.g. Code Interpreter) for Automation Studio."""
        url = "/api/v1/settings/agents/tools/"
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIsInstance(response.data, list)
        tool_names = [item["tool_name"] for item in response.data if isinstance(item, dict)]
        self.assertIn("code_interpreter", tool_names)
        self.assertIn("web_search", tool_names)
        self.assertIn("file_search", tool_names)
        self.assertIn("image_generation", tool_names)
        code_interpreter = next(i for i in response.data if i.get("tool_name") == "code_interpreter")
        self.assertEqual(code_interpreter.get("tool_type"), "builtin")
        self.assertIn("defaults", code_interpreter)
        self.assertEqual(code_interpreter["defaults"].get("display_name"), "Code Interpreter")

    def test_agent_tools_list_includes_repo_custom_tools_without_sync_rows(self) -> None:
        """Runtime repo tools should be listed even when the tenant has no persisted tool rows."""
        response = self.client.get("/api/v1/settings/agents/tools/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        tool_names = [item["tool_name"] for item in response.data if isinstance(item, dict)]
        self.assertIn("search_product", tool_names)

        search_product = next(i for i in response.data if i.get("tool_name") == "search_product")
        self.assertEqual(search_product.get("tool_type"), "custom")
        self.assertTrue(search_product.get("enabled"))
        self.assertIn("defaults", search_product)
        self.assertEqual(search_product["defaults"].get("type"), "custom")

    def test_agent_tools_list_normalizes_legacy_repo_tool_type(self) -> None:
        """Persisted repo tools incorrectly marked as builtin should still be exposed as custom."""
        TenantToolConfiguration.objects.create(
            tenant=self.tenant,
            tool_name="search_product",
            tool_type="builtin",
            enabled=False,
            custom_display_name="Buscar producto",
            custom_description="Custom repo tool description",
            default_params={"foo": "bar"},
        )

        response = self.client.get("/api/v1/settings/agents/tools/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        search_product = next(i for i in response.data if i.get("tool_name") == "search_product")
        self.assertEqual(search_product.get("tool_type"), "custom")
        self.assertFalse(search_product.get("enabled"))
        self.assertEqual(search_product.get("custom_display_name"), "Buscar producto")
        self.assertEqual(search_product.get("custom_description"), "Custom repo tool description")
        self.assertEqual(search_product.get("default_params"), {"foo": "bar"})

    def test_preferences_get_and_patch(self) -> None:
        get_url = "/api/v1/settings/preferences/"
        response = self.client.get(get_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("user_preferences", response.data)

        patch = self.client.patch(
            get_url,
            {"theme": "dark", "notifications": {"email": False}},
            format="json",
        )
        self.assertEqual(patch.status_code, status.HTTP_200_OK)
        self.assertEqual(patch.data["preferences"]["theme"], "dark")
        self.assertFalse(patch.data["preferences"]["notifications"]["email"])
