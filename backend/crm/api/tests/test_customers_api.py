from __future__ import annotations

from django.contrib.auth import get_user_model
from django.db.models.signals import post_save
from django.test.utils import override_settings
from rest_framework import status
from rest_framework.test import APITestCase

from crm.api.tests.utils import ensure_schema
from central_hub.signals import create_internal_contact, seed_tenant_crm_defaults
from tenancy.models import Tenant
from tenancy.signals import create_user_profile, seed_tenant_entitlements

ensure_schema()


@override_settings(ROOT_URLCONF="crm.api.tests.urls")
class CustomersApiTests(APITestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        post_save.disconnect(seed_tenant_entitlements, sender=Tenant)
        post_save.disconnect(seed_tenant_crm_defaults, sender=Tenant)
        cls._user_model = get_user_model()
        post_save.disconnect(create_internal_contact, sender=cls._user_model)
        post_save.disconnect(create_user_profile, sender=cls._user_model)

    @classmethod
    def tearDownClass(cls):
        post_save.connect(create_user_profile, sender=cls._user_model)
        post_save.connect(create_internal_contact, sender=cls._user_model)
        post_save.connect(seed_tenant_crm_defaults, sender=Tenant)
        post_save.connect(seed_tenant_entitlements, sender=Tenant)
        super().tearDownClass()

    def setUp(self):
        self.tenant = Tenant.objects.create(nombre="Customers Tenant", domain="customers.test", subdomain="customers")
        self.user = self._user_model.objects.create_user(
            email="admin@customers.test",
            username="customers-admin",
            password="pass1234",
            tenant=self.tenant,
        )
        self.client.force_authenticate(self.user)

    def test_create_customer_for_authenticated_tenant(self):
        response = self.client.post(
            "/api/v1/crm/customers/",
            {
                "name": "Acme SRL",
                "legal_name": "Acme Sociedad de Responsabilidad Limitada",
                "type": "business",
                "enabled": True,
                "email": "info@acme.test",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        self.assertEqual(response.data["name"], "Acme SRL")
        self.assertEqual(response.data["email"], "info@acme.test")
