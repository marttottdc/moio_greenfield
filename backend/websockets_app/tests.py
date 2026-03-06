from unittest.mock import AsyncMock

from asgiref.sync import async_to_sync
from django.test import SimpleTestCase

from websockets_app.consumers.robot_runs import RobotRunConsumer


class _FakeChannelLayer:
    def __init__(self):
        self.group_add = AsyncMock()
        self.group_discard = AsyncMock()


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
