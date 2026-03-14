import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock

from asgiref.sync import async_to_sync
from django.test import SimpleTestCase, TestCase
from django.utils import timezone

from chatbot.models.agent_configuration import CHANNEL_SHOPIFY_WEBCHAT, AgentConfiguration
from chatbot.models.agent_session import AgentSession
from crm.models import Contact
from websockets_app.consumers.shopify_storefront_chat import ShopifyStorefrontChatConsumer
from central_hub.models import Tenant

try:
    from websockets_app.consumers.robot_runs import RobotRunConsumer
except ModuleNotFoundError:
    RobotRunConsumer = None


class _FakeChannelLayer:
    def __init__(self):
        self.group_add = AsyncMock()
        self.group_discard = AsyncMock()


@unittest.skipIf(RobotRunConsumer is None, "RobotRunConsumer is not available in this test environment")
class RobotRunConsumerStreamingTests(SimpleTestCase):
    def _build_consumer(self):
        consumer = RobotRunConsumer()
        consumer.tenant_id = "tenant-1"
        consumer.robot_id = "robot-1"
        consumer.channel_name = "channel-1"
        consumer.channel_layer = _FakeChannelLayer()
        consumer.send_json = AsyncMock()
        consumer.send_error = AsyncMock()
        consumer.groups = ["robot_run_tenant-1_robot-1"]
        return consumer

    def test_start_streaming_discards_previous_run_group_before_switching(self):
        consumer = self._build_consumer()
        consumer.run_id = "run-a"
        old_group = "robot_run_tenant-1_robot-1_run-a"
        new_group = "robot_run_tenant-1_robot-1_run-b"
        consumer.groups.append(old_group)

        async_to_sync(consumer.start_streaming)({"run_id": "run-b"})

        consumer.channel_layer.group_discard.assert_awaited_once_with(old_group, "channel-1")
        consumer.channel_layer.group_add.assert_awaited_once_with(new_group, "channel-1")
        self.assertEqual(consumer.run_id, "run-b")
        self.assertNotIn(old_group, consumer.groups)
        self.assertIn(new_group, consumer.groups)

    def test_start_streaming_with_missing_run_id_keeps_current_subscription(self):
        consumer = self._build_consumer()
        consumer.run_id = "run-a"
        old_group = "robot_run_tenant-1_robot-1_run-a"
        consumer.groups.append(old_group)

        async_to_sync(consumer.start_streaming)({})

        consumer.send_error.assert_awaited_once_with("Missing run_id")
        consumer.channel_layer.group_discard.assert_not_awaited()
        consumer.channel_layer.group_add.assert_not_awaited()
        self.assertEqual(consumer.run_id, "run-a")
        self.assertIn(old_group, consumer.groups)


class ShopifyStorefrontChatConsumerTests(SimpleTestCase):
    def test_handle_init_passes_requested_session_id_through(self):
        consumer = ShopifyStorefrontChatConsumer()
        tenant = SimpleNamespace(pk="tenant-1", schema_name=None)
        contact = SimpleNamespace(pk="contact-1")
        agent = SimpleNamespace(name="Storefront Agent", id="agent-1")
        session = SimpleNamespace(session="sess-123")

        consumer.send_json = AsyncMock()
        consumer.close = AsyncMock()
        consumer.resolve_tenant_and_contact = AsyncMock(
            return_value={"tenant_id": tenant.pk, "tenant": tenant, "contact": contact}
        )
        consumer.get_agent_for_tenant = AsyncMock(
            return_value={"agent": agent, "tenant_config": object()}
        )
        consumer.get_or_create_session = AsyncMock(return_value={"session": session})

        async_to_sync(consumer.handle_init)(
            {
                "shop_domain": "shop.example.com",
                "anonymous_id": "anon-1",
                "session_id": "sess-123",
            }
        )

        consumer.get_or_create_session.assert_awaited_once_with(
            contact, requested_session_id="sess-123"
        )
        consumer.send_json.assert_awaited_once_with(
            {
                "event_type": "session_started",
                "payload": {
                    "conversation_id": "sess-123",
                    "agent_name": "Storefront Agent",
                    "session_id": "sess-123",
                },
            }
        )


class ShopifyStorefrontChatSessionReuseTests(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(
            nombre="Shop Tenant",
            domain="shop.example.com",
            subdomain="shop",
            schema_name="public",
        )
        self.contact = Contact.objects.create(
            tenant=self.tenant,
            fullname="Storefront visitor",
            email="",
            phone="",
            source="shopify_webchat",
            external_ids={"shopify_webchat_anonymous": "anon-1"},
        )
        self.agent = AgentConfiguration.objects.create(
            tenant=self.tenant,
            name="Storefront Agent",
            channel=CHANNEL_SHOPIFY_WEBCHAT,
            enabled=True,
        )
        self.consumer = ShopifyStorefrontChatConsumer()
        self.consumer.tenant = self.tenant
        self.consumer.tenant_id = self.tenant.pk
        self.consumer.agent_config = self.agent
        self.consumer.shop_domain = "shop.example.com"

    def test_get_or_create_session_reactivates_requested_session(self):
        existing = AgentSession.objects.create(
            tenant=self.tenant,
            contact=self.contact,
            channel=CHANNEL_SHOPIFY_WEBCHAT,
            start=timezone.now(),
            end=timezone.now(),
            last_interaction=timezone.now(),
            current_agent=self.agent.name,
            started_by="user",
            agent_id=self.agent.id,
            active=False,
        )

        result = self.consumer.get_or_create_session.__wrapped__(
            self.consumer,
            self.contact,
            requested_session_id=str(existing.pk),
        )

        self.assertEqual(result["session"].pk, existing.pk)
        existing.refresh_from_db()
        self.assertTrue(existing.active)
        self.assertIsNone(existing.end)
