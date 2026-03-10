from django.contrib.auth import get_user_model
from django.db.models.signals import post_save
from django.test.utils import override_settings
from rest_framework import status
from rest_framework.authtoken.models import Token
from rest_framework.test import APITestCase

from crm.api.tests.utils import ensure_schema
from crm.models import Contact, ContactType
from central_hub.models import Tenant
from central_hub.signals import create_internal_contact, create_tenant_configurations

ensure_schema()


@override_settings(ROOT_URLCONF="crm.api.tests.urls")
class ContactApiTests(APITestCase):
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
        self.tenant = Tenant.objects.create(nombre="Contact Tenant", domain="contacts.test")
        self.user = self.user_model.objects.create_user(
            email="contact-user@example.com",
            username="contact-user",
            password="pass1234",
            tenant=self.tenant,
            first_name="Contact",
            last_name="User",
        )
        self.token = Token.objects.create(user=self.user)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {self.token.key}")
        self.contact_type = ContactType.objects.create(name="Lead", tenant=self.tenant)
        self.contact = Contact.objects.create(
            tenant=self.tenant,
            fullname="Existing Contact",
            email="existing@example.com",
            phone="+598111111",
            company="Acme Corp",
            ctype=self.contact_type,
            created_by=self.user,
            brief_facts={
                "tags": ["vip"],
                "custom_fields": {"source": "import"},
                "activity_summary": {"total_messages": 12, "total_tickets": 1},
            },
        )

    def test_list_contacts_returns_database_records(self):
        response = self.client.get("/api/v1/public/contacts/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["pagination"]["total_items"], 1)
        contact_payload = response.data["contacts"][0]
        self.assertEqual(contact_payload["name"], "Existing Contact")
        self.assertEqual(contact_payload["tags"], ["vip"])
        self.assertEqual(contact_payload["type"], "Lead")

    def test_create_contact_persists_and_returns_payload(self):
        payload = {
            "name": "API Contact",
            "email": "api@example.com",
            "phone": "+598999999",
            "company": "Moio",
            "type": str(self.contact_type.id),
            "tags": ["new"],
            "custom_fields": {"source": "api"},
        }
        response = self.client.post("/api/v1/public/contacts/", payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["name"], payload["name"])
        self.assertEqual(response.data["tags"], payload["tags"])
        self.assertTrue(Contact.objects.filter(fullname="API Contact").exists())

    def test_create_contact_normalizes_phone_with_spaces_returns_201(self):
        """Google Places-style international_phone_number with spaces is normalized and accepted."""
        payload = {
            "fullname": "Phone Len Test",
            "company": "Phone Len Test",
            "phone": "+598 95 750 350",
            "source": "google_places",
            "tags": ["google-places"],
            "custom_fields": {"google_place_id": "test_place_id"},
            "type": str(self.contact_type.id),
        }
        response = self.client.post("/api/v1/public/contacts/", payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        contact = Contact.objects.get(fullname="Phone Len Test")
        self.assertIsNotNone(contact.phone)
        self.assertLessEqual(len(contact.phone), 15)
        self.assertNotIn(" ", contact.phone)

    def test_create_contact_phone_too_long_returns_400(self):
        """Phone longer than max length after normalization returns 400 JSON, not 500."""
        payload = {
            "fullname": "Phone Len Test",
            "company": "Phone Len Test",
            "phone": "+598957503501234567",
            "source": "google_places",
            "tags": ["google-places"],
            "custom_fields": {"google_place_id": "test_place_id"},
            "type": str(self.contact_type.id),
        }
        response = self.client.post("/api/v1/public/contacts/", payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["error"], "invalid_request")
        self.assertIn("details", response.data)
        self.assertIn("phone", response.data["details"])
        self.assertFalse(Contact.objects.filter(fullname="Phone Len Test").exists())

    def test_create_contact_omit_phone_returns_201(self):
        """Omitting phone is allowed (empty string after normalization)."""
        payload = {
            "fullname": "No Phone Contact",
            "company": "Acme",
            "type": str(self.contact_type.id),
        }
        response = self.client.post("/api/v1/public/contacts/", payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        contact = Contact.objects.get(fullname="No Phone Contact")
        self.assertEqual(contact.phone, "")

    def test_patch_contact_updates_metadata(self):
        payload = {
            "name": "Updated Contact",
            "tags": ["vip", "tech"],
            "custom_fields": {"stage": "demo"},
        }
        url = f"/api/v1/public/contacts/{self.contact.pk}/"
        response = self.client.patch(url, payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["name"], "Updated Contact")
        self.assertEqual(response.data["tags"], ["vip", "tech"])
        self.contact.refresh_from_db()
        self.assertEqual(self.contact.fullname, "Updated Contact")
        self.assertEqual(self.contact.brief_facts["custom_fields"], {"stage": "demo"})

    def test_delete_contact_removes_record(self):
        url = f"/api/v1/public/contacts/{self.contact.pk}/"
        response = self.client.delete(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertFalse(Contact.objects.filter(pk=self.contact.pk).exists())

    def test_export_endpoint_uses_real_queryset(self):
        Contact.objects.create(
            tenant=self.tenant,
            fullname="Second Contact",
            email="second@example.com",
            phone="+598123456",
            company="Acme Corp",
            ctype=self.contact_type,
            created_by=self.user,
            brief_facts={"tags": ["vip", "tech"]},
        )
        response = self.client.get("/api/v1/public/contacts/export/?format=json&type=Lead&tags=vip")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertGreaterEqual(response.data["total_contacts"], 1)
        self.assertTrue(response.data["preview"])
        self.assertEqual(response.data["filters"]["type"], "Lead")
