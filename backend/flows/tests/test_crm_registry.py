from django.contrib.auth import get_user_model
from django.test import TestCase

from rest_framework.test import APIRequestFactory, force_authenticate

from flows import views
from flows.core.registry import get_executor


User = get_user_model()


class CrmRegistryApiTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="tester", password="pass")
        self.factory = APIRequestFactory()

    def test_models_endpoint_returns_resources(self):
        request = self.factory.get("/api/v1/flows/crm/models/")
        force_authenticate(request, user=self.user)
        resp = views.api_flow_crm_models(request)
        self.assertEqual(resp.status_code, 200)
        payload = resp.data
        self.assertTrue(payload.get("ok"))
        slugs = [m.get("slug") for m in payload.get("models", [])]
        self.assertIn("contact", slugs)
        self.assertIn("ticket", slugs)
        self.assertIn("deal", slugs)
        self.assertIn("audience", slugs)

    def test_detail_endpoint_returns_ops_and_schemas(self):
        request = self.factory.get("/api/v1/flows/crm/contact/")
        force_authenticate(request, user=self.user)
        resp = views.api_flow_crm_model_detail(request, slug="contact")
        self.assertEqual(resp.status_code, 200)
        payload = resp.data
        self.assertTrue(payload.get("ok"))
        model = payload.get("model") or {}
        ops = (model.get("operations") or {}).keys()
        self.assertIn("create", ops)
        self.assertIn("get", ops)
        create = (model.get("operations") or {}).get("create") or {}
        self.assertIn("input_schema", create)
        self.assertIn("output_schema", create)


class CrmCrudNodeTests(TestCase):
    def test_crm_crud_executor_sandbox_resolves_ctx_templates(self):
        executor = get_executor("tool_crm_crud")
        node = {
            "id": "n1",
            "kind": "tool_crm_crud",
            "config": {
                "resource_slug": "contact",
                "operation": "create",
                "input": {
                    "fullname": "{{ ctx.event.fullname }}",
                    "phone": "{{ ctx.event.phone }}",
                },
            },
        }
        ctx = {
            "$sandbox": True,
            "tenant_id": "tenant-1",
            "event": {"fullname": "Alice", "phone": "+111"},
        }
        result = executor(node, payload={}, ctx=ctx)
        self.assertEqual(result.get("success"), True)
        self.assertEqual(result.get("id"), "sandbox-id")
        self.assertEqual(result.get("object", {}).get("fullname"), "Alice")
        self.assertEqual(result.get("object", {}).get("phone"), "+111")

