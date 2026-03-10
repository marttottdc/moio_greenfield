from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.db.models.signals import post_save
from django.test.utils import override_settings
from django.utils import timezone
from rest_framework import status
from rest_framework.authtoken.models import Token
from rest_framework.test import APITestCase

from chatbot.models.chatbot_session import ChatbotMemory, ChatbotSession
from crm.api.tests.utils import ensure_schema
from crm.models import Contact, ContactType
from central_hub.models import Tenant
from central_hub.signals import create_internal_contact, create_tenant_configurations

ensure_schema()


@override_settings(ROOT_URLCONF="crm.api.tests.urls")
class CommunicationsApiTests(APITestCase):
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
        self.tenant = Tenant.objects.create(nombre="Comms Tenant", domain="comms.test")
        self.user = self.user_model.objects.create_user(
            email="comms-user@example.com",
            username="comms-user",
            password="pass1234",
            tenant=self.tenant,
            first_name="Comms",
            last_name="User",
        )
        self.token = Token.objects.create(user=self.user)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {self.token.key}")

        self.contact_type = ContactType.objects.create(name="Lead", tenant=self.tenant)
        self.contact = Contact.objects.create(
            tenant=self.tenant,
            fullname="Conversation Contact",
            phone="+598123456",
            ctype=self.contact_type,
            created_by=self.user,
        )
        self.session = ChatbotSession.objects.create(
            tenant=self.tenant,
            contact=self.contact,
            channel="whatsapp",
            start=timezone.now(),
            last_interaction=timezone.now(),
            started_by="api-tests",
            context={
                "human_mode_messages": [
                    {"role": "assistant", "content": "existing message"},
                ]
            },
            human_mode=True,
            active=True,
        )

    def test_human_mode_rejects_list_content(self):
        payload = {
            "content": [
                "first message",
                "second message",
            ]
        }
        url = f"/api/v1/public/communications/conversations/{self.session.pk}/messages/"

        response = self.client.post(url, payload, format="json")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["error"], "invalid_request")
        self.assertEqual(response.data["message"], "content must be a string in human mode")
        self.assertFalse(ChatbotMemory.objects.filter(session=self.session).exists())

    def test_human_mode_send_persists_single_delivered_item(self):
        payload = {"content": "single message"}
        url = f"/api/v1/public/communications/conversations/{self.session.pk}/messages/"

        with patch("central_hub.models.TenantConfiguration.objects.get") as tenant_config_get, patch(
            "chatbot.core.messenger.Messenger"
        ) as messenger_cls:
            tenant_config_get.return_value = object()
            messenger = messenger_cls.return_value
            messenger.just_reply_with_report.return_value = {
                "success": True,
                "sent_items": [payload["content"]],
                "failed_items": [],
            }

            response = self.client.post(url, payload, format="json")

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["message"]["content"], payload["content"])

        sent_messages = list(
            ChatbotMemory.objects.filter(session=self.session)
            .order_by("created")
            .values_list("content", flat=True)
        )
        self.assertEqual(sent_messages, [payload["content"]])

        self.session.refresh_from_db()
        history = self.session.context
        self.assertEqual(
            history,
            [
                {"role": "assistant", "content": "existing message"},
                {"role": "assistant", "content": payload["content"]},
            ],
        )

        messenger.just_reply_with_report.assert_called_once_with(
            payload["content"],
            self.contact.phone,
        )
