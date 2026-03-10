from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import SimpleTestCase, TestCase
from django.urls import resolve, reverse
from rest_framework.test import APIClient

from central_hub.integrations.v1.views.email import EmailAccountsView
from central_hub.integrations.v1.models import ExternalAccount, EmailAccount, CalendarAccount
from central_hub.integrations.v1.services.accounts import ensure_user_slot_available
from central_hub.integrations.v1 import urls as v1_urls  # ensure import doesn't blow up
from central_hub.models import Tenant


class RoutingTests(SimpleTestCase):
    def test_email_accounts_route_not_captured_by_slug(self):
        match = resolve("/api/v1/integrations/email/accounts")
        self.assertEqual(match.func.view_class, EmailAccountsView)


class IntegrationV1PermissionTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.User = get_user_model()
        self.tenant = Tenant.objects.create(nombre="Acme", domain="acme.test")

        self.admin = self.User.objects.create_user(email="admin@acme.test", username="admin", password="x", tenant=self.tenant)
        self.member = self.User.objects.create_user(email="user@acme.test", username="user", password="x", tenant=self.tenant)

        tenant_admin_group, _ = Group.objects.get_or_create(name="tenant_admin")
        self.admin.groups.add(tenant_admin_group)

    def test_flow_accounts_tenant_scope_requires_admin(self):
        self.client.force_authenticate(user=self.member)
        resp = self.client.get("/api/v1/integrations/email/flow/accounts?scope=tenant")
        self.assertEqual(resp.status_code, 403)

    def test_flow_accounts_user_scope_returns_only_self(self):
        external = ExternalAccount.objects.create(
            tenant=self.tenant,
            provider="imap",
            ownership="user",
            owner_user=self.member,
            email_address=self.member.email,
            credentials={"host": "imap.test", "username": "u", "password": "p"},
        )
        EmailAccount.objects.create(tenant=self.tenant, external_account=external)

        self.client.force_authenticate(user=self.member)
        resp = self.client.get("/api/v1/integrations/email/flow/accounts?scope=user")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.json()), 1)
        self.assertEqual(resp.json()[0]["external_account"]["email_address"], self.member.email)

    def test_user_slot_enforced(self):
        ExternalAccount.objects.create(
            tenant=self.tenant,
            provider="imap",
            ownership="user",
            owner_user=self.member,
            email_address=self.member.email,
            credentials={"host": "imap.test", "username": "u", "password": "p"},
        )
        with self.assertRaises(Exception):
            ensure_user_slot_available(self.member)

    def test_email_messages_list_route(self):
        match = resolve(f"/api/v1/integrations/email/accounts/{uuid.uuid4()}/messages")
        self.assertEqual(match.url_name, "integrations_email_messages")

    def test_calendar_events_list_route(self):
        match = resolve(f"/api/v1/integrations/calendar/accounts/{uuid.uuid4()}/events")
        self.assertEqual(match.url_name, "integrations_calendar_events")

