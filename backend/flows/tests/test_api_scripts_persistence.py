import json
import uuid

from django.test import TestCase
from django.urls import reverse

from central_hub.models import MoioUser, Tenant, TenantConfiguration
from flows.models import Flow, FlowVersion, FlowVersionStatus


class ApiScriptsPersistenceTests(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(
            nombre="Acme Corp",
            enabled=True,
            domain="acme.test",
        )
        TenantConfiguration.objects.get_or_create(tenant=self.tenant)
        self.user = MoioUser.objects.create_user(
            email="user@example.com",
            username="user",
            password="secret",
            tenant=self.tenant,
        )
        self.client.force_login(self.user)

        self.flow = Flow.objects.create(
            tenant=self.tenant,
            name="Flow One",
            description="",
            status="active",
            created_by=self.user,
        )
        FlowVersion.objects.create(
            flow=self.flow,
            tenant=self.tenant,
            version=1,
            status=FlowVersionStatus.DRAFT,
            graph={"nodes": [], "edges": [], "meta": {"draft": True}},
        )

    def test_api_scripts_persists_params_across_versions_and_is_exposed_to_flow_builder(self):
        create_payload = {
            "name": "Normalize payload",
            "description": "Test script",
            "code": "def main(params):\n    return params\n",
            "params": {"foo": "bar", "count": 1},
        }
        resp = self.client.post(
            reverse("api_script_list"),
            data=json.dumps(create_payload),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 201)
        created = resp.json()
        script_id = created.get("id")
        self.assertTrue(script_id)
        self.assertEqual(
            created["latest_version"]["parameters"],
            create_payload["params"],
        )

        patch_payload = {
            "name": "Normalize payload",
            "description": "Updated",
            "code": "def main(params):\n    return {'ok': True, 'params': params}\n",
            "params": {"foo": "baz", "count": 2},
            "notes": "v2",
        }
        resp = self.client.patch(
            reverse("api_script_detail", args=[uuid.UUID(script_id)]),
            data=json.dumps(patch_payload),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 200)
        updated = resp.json()
        self.assertTrue(updated.get("ok"))
        self.assertEqual(updated["script"]["latest_version"]["parameters"], patch_payload["params"])
        self.assertEqual(updated["script"]["latest_version"]["version"], 2)

        # Detail GET returns the latest persisted parameters.
        resp = self.client.get(reverse("api_script_detail", args=[uuid.UUID(script_id)]))
        self.assertEqual(resp.status_code, 200)
        detail = resp.json()["script"]
        self.assertEqual(detail["latest_version"]["parameters"], patch_payload["params"])

        # List GET includes latest version body + parameters.
        resp = self.client.get(reverse("api_script_list"))
        self.assertEqual(resp.status_code, 200)
        listing = resp.json()["scripts"]
        found = next((s for s in listing if s["id"] == script_id), None)
        self.assertIsNotNone(found)
        self.assertEqual(found["latest_version"]["parameters"], patch_payload["params"])
        self.assertIsNone(found.get("flow_id"))  # not linked to a specific flow

        # Flow detail payload (used by React builder) includes tenant-wide scripts.
        resp = self.client.get(reverse("flows_api:api_flow_detail", args=[self.flow.id]))
        self.assertEqual(resp.status_code, 200)
        flow_payload = resp.json()
        scripts = flow_payload.get("scripts") or []
        found_in_flow = next((s for s in scripts if s["id"] == script_id), None)
        self.assertIsNotNone(found_in_flow)
        self.assertEqual(found_in_flow["latest_version"]["parameters"], patch_payload["params"])

