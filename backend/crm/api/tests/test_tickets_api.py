from django.contrib.auth import get_user_model
from django.db.models.signals import post_save
from django.test.utils import override_settings
from rest_framework import status
from rest_framework.authtoken.models import Token
from rest_framework.test import APITestCase

from crm.api.tests.utils import ensure_schema
from crm.models import Contact, Ticket, TicketComment
from central_hub.models import Tenant, TenantConfiguration
from central_hub.signals import create_internal_contact, create_tenant_configurations

ensure_schema()


@override_settings(ROOT_URLCONF="crm.api.tests.urls")
class TicketApiTests(APITestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        post_save.disconnect(create_tenant_configurations, sender=Tenant)
        cls.user_model = get_user_model()
        post_save.disconnect(create_internal_contact, sender=cls.user_model)

    @classmethod
    def tearDownClass(cls):
        post_save.connect(create_tenant_configurations, sender=Tenant)
        post_save.connect(create_internal_contact, sender=cls.user_model)
        super().tearDownClass()

    def setUp(self):
        self.tenant = Tenant.objects.create(nombre="Ticket Tenant", domain="tickets.test")
        TenantConfiguration.objects.create(tenant=self.tenant)
        self.user = self.user_model.objects.create_user(
            email="tickets@example.com",
            username="tickets-user",
            password="pass1234",
            tenant=self.tenant,
            first_name="Ticket",
            last_name="User",
        )
        self.token = Token.objects.create(user=self.user)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {self.token.key}")

        self.user_contact = Contact.objects.create(
            tenant=self.tenant,
            email=self.user.email,
            fullname="Agent User",
        )
        self.customer_contact = Contact.objects.create(
            tenant=self.tenant,
            fullname="Customer Contact",
            email="customer@example.com",
        )
        self.ticket = Ticket.objects.create(
            tenant=self.tenant,
            creator=self.customer_contact,
            description="Existing issue",
            service="support",
            type="I",
            status="O",
        )
        self.comment = TicketComment.objects.create(
            ticket=self.ticket,
            creator=self.user_contact,
            comment="First note",
        )

    def test_list_tickets_returns_open_records(self):
        Ticket.objects.create(
            tenant=self.tenant,
            creator=self.customer_contact,
            description="Closed issue",
            service="support",
            type="I",
            status="C",
        )

        response = self.client.get("/api/v1/public/tickets/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["pagination"]["total_items"], 1)
        self.assertEqual(response.data["tickets"][0]["description"], "Existing issue")

    def test_create_ticket_persists_payload(self):
        payload = {
            "description": "New API ticket",
            "service": "support",
            "type": "I",
            "creator_id": str(self.customer_contact.pk),
        }
        response = self.client.post("/api/v1/public/tickets/", payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["description"], payload["description"])
        self.assertTrue(Ticket.objects.filter(description="New API ticket").exists())

    def test_ticket_detail_includes_comments(self):
        url = f"/api/v1/public/tickets/{self.ticket.pk}/"
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data["comments"]), 1)
        self.assertEqual(response.data["comments"][0]["comment"], "First note")

    def test_add_comment_to_ticket(self):
        url = f"/api/v1/public/tickets/{self.ticket.pk}/comments/"
        response = self.client.post(url, {"comment": "Second note"}, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertTrue(TicketComment.objects.filter(comment="Second note").exists())

    def test_ticket_summary_returns_counts(self):
        Ticket.objects.create(
            tenant=self.tenant,
            creator=self.customer_contact,
            description="Planned work",
            service="support",
            type="P",
            status="O",
        )
        response = self.client.get("/api/v1/public/tickets/summary/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertGreaterEqual(response.data["open"], 1)
