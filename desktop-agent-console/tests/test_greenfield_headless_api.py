from __future__ import annotations

import unittest

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from rest_framework.test import APIClient


TEST_MIDDLEWARE = [entry for entry in settings.MIDDLEWARE if entry != "django_tenants.middleware.main.TenantMainMiddleware"]


@override_settings(MIDDLEWARE=TEST_MIDDLEWARE)
@unittest.skipIf(getattr(settings, "DJANGO_TENANTS_ENABLED", False), "Greenfield API tests run in non-tenant mode")
class GreenfieldHeadlessApiTests(TestCase):
    def setUp(self) -> None:
        user_model = get_user_model()
        self.user = user_model.objects.create_user(
            username="crm-user",
            email="crm@example.com",
            password="test-password",
        )
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)
        self.client.credentials(HTTP_X_WORKSPACE="main")

    def test_crm_core_flow_with_customers(self) -> None:
        root_catalog = self.client.get("/api/v1/meta/endpoints/")
        self.assertEqual(root_catalog.status_code, 200)
        self.assertIn("crm", root_catalog.data.get("modules", {}))

        catalog = self.client.get("/api/v1/crm/meta/endpoints/")
        self.assertEqual(catalog.status_code, 200)
        self.assertEqual(catalog.data.get("module"), "crm")

        pipeline_res = self.client.post("/api/v1/crm/pipelines/create-default/", {}, format="json")
        self.assertEqual(pipeline_res.status_code, 201)
        stage_id = pipeline_res.data["stages"][0]["id"]
        pipeline_id = pipeline_res.data["id"]

        company_res = self.client.post(
            "/api/v1/crm/companies/",
            {"name": "Moio Labs"},
            format="json",
        )
        self.assertEqual(company_res.status_code, 201)
        company_id = company_res.data["id"]

        contact_res = self.client.post(
            "/api/v1/crm/contacts/",
            {
                "first_name": "Ana",
                "last_name": "Pérez",
                "email": "ana@example.com",
                "status": "lead",
                "company": company_id,
            },
            format="json",
        )
        self.assertEqual(contact_res.status_code, 201)
        contact_id = contact_res.data["id"]

        customer_res = self.client.post(
            "/api/v1/crm/customers/",
            {
                "contact": contact_id,
                "lifecycle": "active",
                "segment": "enterprise",
                "health_score": "82.00",
            },
            format="json",
        )
        self.assertEqual(customer_res.status_code, 201)

        deal_res = self.client.post(
            "/api/v1/crm/deals/",
            {
                "title": "Moio Expansion",
                "pipeline": pipeline_id,
                "stage": stage_id,
                "contact": contact_id,
                "company": company_id,
                "amount": "12000.00",
                "currency": "USD",
            },
            format="json",
        )
        self.assertEqual(deal_res.status_code, 201)

        dashboard_res = self.client.get("/api/v1/crm/dashboard/summary/")
        self.assertEqual(dashboard_res.status_code, 200)
        self.assertEqual(dashboard_res.data["customers"], 1)
        self.assertEqual(dashboard_res.data["openDeals"], 1)

    def test_integrations_module_and_instance_test(self) -> None:
        catalog = self.client.get("/api/v1/integrations/meta/endpoints/")
        self.assertEqual(catalog.status_code, 200)
        self.assertEqual(catalog.data.get("module"), "integrations")

        list_res = self.client.get("/api/v1/integrations/")
        self.assertEqual(list_res.status_code, 200)
        self.assertTrue(any(row.get("slug") == "openai" for row in list_res.data))

        create_res = self.client.post(
            "/api/v1/integrations/openai/",
            {
                "name": "openai-primary",
                "config": {"model": "gpt-5"},
                "secret_refs": {"api_key": "vault://openai/prod"},
                "status": "disconnected",
            },
            format="json",
        )
        self.assertEqual(create_res.status_code, 201)
        instance_id = create_res.data["id"]

        test_res = self.client.post(
            f"/api/v1/integrations/openai/{instance_id}/test/",
            {},
            format="json",
        )
        self.assertEqual(test_res.status_code, 200)
        self.assertTrue(test_res.data["ok"])

    def test_meta_endpoint_catalog_supports_search_and_filters(self) -> None:
        res = self.client.get("/api/v1/meta/endpoints/?module=crm&method=POST&q=contact&limit=50")
        self.assertEqual(res.status_code, 200)
        stats = res.data.get("stats", {})
        self.assertGreaterEqual(stats.get("count", 0), 1)
        for row in res.data.get("endpoints", []):
            self.assertEqual(row.get("module"), "crm")
            self.assertEqual(row.get("method"), "POST")
            joined = f"{row.get('name', '')} {row.get('path', '')}".lower()
            self.assertIn("contact", joined)

    def test_meta_endpoint_catalog_returns_call_contract_fields(self) -> None:
        res = self.client.get("/api/v1/meta/endpoints/?module=integrations&path=/test/")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data.get("format"), "compact")
        self.assertTrue(str(res.data.get("base_url", "")).startswith("http"))
        rows = res.data.get("endpoints", [])
        self.assertGreaterEqual(len(rows), 1)
        row = rows[0]
        self.assertIn("path", row)
        self.assertIn("input", row)
        self.assertIn("output", row)
        self.assertIn("resource", row)
        self.assertIn("capability", row)
        self.assertTrue(str(row.get("absolute_url", "")).startswith("http"))

    def test_meta_endpoint_catalog_verbose_mode_keeps_full_contract(self) -> None:
        res = self.client.get("/api/v1/meta/endpoints/?module=integrations&path=/test/&detail=verbose")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data.get("format"), "verbose")
        rows = res.data.get("endpoints", [])
        self.assertGreaterEqual(len(rows), 1)
        row = rows[0]
        self.assertIn("call_example", row)
        self.assertIn("body", row)
        self.assertIn("response", row)
        self.assertTrue(str(row.get("call_example", "")).startswith("curl -X"))

    def test_meta_endpoint_catalog_accepts_search_aliases_and_semantic_terms(self) -> None:
        res = self.client.get("/api/v1/meta/endpoints/?module=crm&search=client")
        self.assertEqual(res.status_code, 200)
        self.assertEqual((res.data.get("filters") or {}).get("q"), "client")
        rows = res.data.get("endpoints", [])
        self.assertGreaterEqual(len(rows), 1)
        self.assertTrue(any(str(row.get("path") or "").startswith("/api/v1/crm/customers/") for row in rows))

    def test_meta_endpoint_catalog_short_mode_returns_minimal_rows(self) -> None:
        res = self.client.get("/api/v1/meta/endpoints/?module=crm&s=ticket&detail=short")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data.get("format"), "short")
        rows = res.data.get("endpoints", [])
        self.assertGreaterEqual(len(rows), 1)
        row = rows[0]
        self.assertIn("path", row)
        self.assertIn("resource", row)
        self.assertIn("capability", row)
        self.assertNotIn("input", row)
        self.assertNotIn("output", row)

    def test_error_response_format_is_standardized(self) -> None:
        anon_client = APIClient()
        res = anon_client.get("/api/v1/meta/endpoints/")
        self.assertIn(res.status_code, {401, 403})
        self.assertIn("error", res.data)
        error = res.data["error"]
        self.assertIn("code", error)
        self.assertIn("message", error)
        self.assertIn("details", error)
        self.assertEqual(res.data.get("status"), res.status_code)
