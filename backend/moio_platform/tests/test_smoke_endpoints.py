"""
Smoke tests: one request per module to ensure endpoints respond.

Run with: pytest backend/moio_platform/tests/test_smoke_endpoints.py -v

Uses main URL conf (moio_platform.urls). Creates one tenant + user, gets JWT,
then GETs (or minimal POST) each endpoint group. Accepts 200/201/204 or
documented 4xx for unauthenticated.
"""
from __future__ import annotations

from django.contrib.auth import get_user_model
from django.db.models.signals import post_save
from django.test import override_settings
from rest_framework import status
from rest_framework.test import APITestCase

from central_hub.models import Tenant
from central_hub.signals import create_internal_contact, create_tenant_configurations


def _login(client, email: str, password: str) -> dict | None:
    resp = client.post(
        "/api/v1/auth/login",
        {"username": email, "password": password},
        format="json",
    )
    if resp.status_code != status.HTTP_200_OK:
        return None
    return resp.data


@override_settings(ROOT_URLCONF="moio_platform.urls")
class SmokeEndpointsTests(APITestCase):
    """Minimal smoke: each module endpoint returns a non-5xx."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        post_save.disconnect(create_tenant_configurations, sender=Tenant)
        cls.User = get_user_model()
        post_save.disconnect(create_internal_contact, sender=cls.User)

    @classmethod
    def tearDownClass(cls):
        post_save.connect(create_internal_contact, sender=cls.User)
        post_save.connect(create_tenant_configurations, sender=Tenant)
        super().tearDownClass()

    def setUp(self):
        self.tenant = Tenant.objects.create(
            nombre="Smoke Tenant",
            domain="smoke.test",
            subdomain="smoke",
            schema_name="smoke",
        )
        self.user = self.User.objects.create_user(
            email="smoke@example.com",
            username="smoke-user",
            password="pass1234",
            tenant=self.tenant,
        )
        login_data = _login(self.client, self.user.email, "pass1234")
        self.assertIsNotNone(login_data, "Login must succeed for smoke tests")
        self.access = login_data["access"]
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {self.access}")

    def _get_ok(self, path: str, msg: str = "") -> None:
        resp = self.client.get(path)
        self.assertIn(
            resp.status_code,
            (status.HTTP_200_OK, status.HTTP_201_CREATED, status.HTTP_204_NO_CONTENT),
            msg or f"GET {path} -> {resp.status_code}",
        )

    def test_health_public(self):
        self.client.credentials()
        resp = self.client.get("/api/v1/health/")
        self.assertIn(resp.status_code, (status.HTTP_200_OK, status.HTTP_204_NO_CONTENT))

    def test_meta_endpoints_public(self):
        self.client.credentials()
        resp = self.client.get("/api/v1/meta/endpoints/")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

    def test_bootstrap_tenant(self):
        self._get_ok("/api/v1/bootstrap/")

    def test_content_navigation(self):
        self._get_ok("/api/v1/content/navigation/")

    def test_users_list(self):
        self._get_ok("/api/v1/users/")

    def test_settings_preferences(self):
        resp = self.client.get("/api/v1/settings/preferences/")
        self.assertIn(resp.status_code, (status.HTTP_200_OK, status.HTTP_404_NOT_FOUND))

    def test_integrations_list(self):
        self._get_ok("/api/v1/integrations/")

    def test_crm_contacts_list(self):
        self._get_ok("/api/v1/crm/contacts/")

    def test_crm_communications_summary(self):
        self._get_ok("/api/v1/crm/communications/summary/")

    def test_crm_tickets_list(self):
        self._get_ok("/api/v1/crm/tickets/")

    def test_crm_dashboard_summary(self):
        self._get_ok("/api/v1/crm/dashboard/summary/")

    def test_crm_templates_list(self):
        self._get_ok("/api/v1/crm/templates/")

    def test_crm_customers_list(self):
        self._get_ok("/api/v1/crm/customers/")

    def test_crm_deals_list(self):
        self._get_ok("/api/v1/crm/deals/")

    def test_activities_list(self):
        self._get_ok("/api/v1/activities/")

    def test_capture_entries_list(self):
        self._get_ok("/api/v1/capture/entries/")

    def test_timeline(self):
        self._get_ok("/api/v1/timeline/")

    def test_resources_whatsapp_templates(self):
        resp = self.client.get("/api/v1/resources/whatsapp-templates/")
        self.assertIn(resp.status_code, (status.HTTP_200_OK, status.HTTP_404_NOT_FOUND))

    def test_campaigns_list(self):
        resp = self.client.get("/api/v1/campaigns/campaigns/")
        self.assertIn(resp.status_code, (status.HTTP_200_OK, status.HTTP_401_UNAUTHORIZED))

    def test_flows_list(self):
        self._get_ok("/api/v1/flows/")

    def test_scripts_list(self):
        self._get_ok("/api/v1/scripts/")

    def test_datalab_panels(self):
        resp = self.client.get("/api/v1/datalab/panels/")
        self.assertIn(resp.status_code, (status.HTTP_200_OK, status.HTTP_404_NOT_FOUND))

    def test_datalab_datasets(self):
        resp = self.client.get("/api/v1/datalab/datasets/")
        self.assertIn(resp.status_code, (status.HTTP_200_OK, status.HTTP_404_NOT_FOUND))

    def test_desktop_agent_sessions(self):
        self._get_ok("/api/v1/desktop-agent/sessions/")

    def test_desktop_agent_status(self):
        self._get_ok("/api/v1/desktop-agent/status/")

    def test_docs_endpoints_list(self):
        self.client.credentials()
        resp = self.client.get("/api/docs/endpoints/")
        self.assertIn(resp.status_code, (status.HTTP_200_OK, status.HTTP_401_UNAUTHORIZED))

    def test_tenant_bootstrap(self):
        self._get_ok("/api/tenant/bootstrap/")
