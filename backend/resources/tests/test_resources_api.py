from __future__ import annotations

from unittest.mock import patch

from crm.api.tests.utils import ensure_schema

ensure_schema()

from django.contrib.auth import get_user_model  # noqa: E402
from django.db.models.signals import post_save  # noqa: E402
from django.test.utils import override_settings  # noqa: E402
from rest_framework import status  # noqa: E402
from rest_framework.test import APITestCase  # noqa: E402

from crm.models import Contact  # noqa: E402
from central_hub.context_utils import current_tenant  # noqa: E402
from central_hub.models import Tenant, TenantConfiguration  # noqa: E402
from central_hub.signals import create_internal_contact, create_tenant_configurations  # noqa: E402


@override_settings(ROOT_URLCONF="crm.api.tests.urls")
class ResourceApiTests(APITestCase):
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
        self.tenant = Tenant.objects.create(nombre="Tenant R", domain="resources.test")
        self.other_tenant = Tenant.objects.create(nombre="Other", domain="other.test")

        self.user = self._user_model.objects.create_user(
            email="resources@example.com",
            username="resources-user",
            password="pass1234",
            tenant=self.tenant,
        )
        self.client.force_authenticate(self.user)

        self.config = TenantConfiguration.objects.create(
            tenant=self.tenant,
            whatsapp_integration_enabled=False,
            whatsapp_name="tenant-r",
        )
        TenantConfiguration.objects.create(tenant=self.other_tenant, whatsapp_name="tenant-other")

        token = current_tenant.set(self.tenant)
        self.addCleanup(lambda: current_tenant.reset(token))

    def test_contact_search_filters_by_query_and_tenant(self) -> None:
        Contact.objects.create(tenant=self.tenant, fullname="John Carter", email="john@example.com")
        Contact.objects.create(tenant=self.other_tenant, fullname="John Other", email="other@example.com")

        response = self.client.get("/api/v1/resources/contacts/search/?q=Jo")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data["results"]), 1)
        self.assertEqual(response.data["results"][0]["fullname"], "John Carter")

    @patch("resources.api.views.WhatsappBusinessClient")
    def test_whatsapp_templates_lists_payload_from_client(self, client_cls) -> None:
        self.config.whatsapp_integration_enabled = True
        self.config.save()

        fake_client = client_cls.return_value
        fake_client.download_message_templates.return_value = [
            {
                "id": "tpl_123",
                "name": "Welcome",
                "category": "MARKETING",
                "language": "en_US",
                "status": "APPROVED",
                "components": [],
            }
        ]

        response = self.client.get("/api/v1/resources/whatsapp-templates/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["templates"][0]["name"], "Welcome")
        fake_client.download_message_templates.assert_called_once()
