from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from portal.models import Tenant, TenantConfiguration
from .models import Flow, FlowVersion


User = get_user_model()


class FlowSmokeTest(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(
            nombre="Test Tenant",
            enabled=True,
            domain="test.local",
        )
        TenantConfiguration.objects.get_or_create(tenant=self.tenant)
        self.user = User.objects.create_user(
            email="flow-smoke@example.com",
            username="flow-smoke",
            password="secret",
            tenant=self.tenant,
        )
        self.client.force_login(self.user)

    def test_create_and_open_builder(self):
        resp = self.client.post(reverse("flows:create"))
        self.assertEqual(resp.status_code, 302)
        flow = Flow.objects.first()
        self.assertIsNotNone(flow)
        self.assertTrue(FlowVersion.objects.filter(flow=flow).exists())

        # React builder is the canonical entrypoint.
        resp = self.client.get(reverse("flows:builder_react", args=[flow.id]))
        self.assertEqual(resp.status_code, 200)
