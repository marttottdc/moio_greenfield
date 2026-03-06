import logging
from typing import Optional

from robots.models import Robot
from websockets_app.consumers.base import TenantAwareConsumer

logger = logging.getLogger(__name__)


class RobotRunConsumer(TenantAwareConsumer):
    channel_prefix = "robot_run"
    requires_auth = True

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.robot_id: Optional[str] = None
        self.run_id: Optional[str] = None

    async def connect(self):
        self.robot_id = self.scope["url_route"]["kwargs"].get("robot_id")
        if not self.robot_id:
            await self.close(code=4000)
            return

        if self.requires_auth:
            authenticated = await self.authenticate()
            if not authenticated:
                await self.close(code=4001)
                return

        # Ensure the robot_id belongs to the authenticated tenant before joining any groups.
        owns_robot = await self.verify_resource_ownership(Robot, self.robot_id)
        if not owns_robot:
            await self.close(code=4003)
            return

        await self.accept()
        await self.setup_groups()
        await self.on_connect()

    async def setup_groups(self):
        if self.tenant_id and self.robot_id:
            group_name = f"robot_run_{self.tenant_id}_{self.robot_id}"
            await self.channel_layer.group_add(group_name, self.channel_name)
            self.groups.append(group_name)

    async def on_connect(self):
        await self.send_json(
            {
                "event_type": "connected",
                "payload": {"robot_id": self.robot_id},
            }
        )

    async def on_message(self, action: str, data: dict):
        if action == "start_stream":
            await self.start_streaming(data)
        elif action == "stop_stream":
            await self.stop_streaming()

    async def start_streaming(self, data: dict):
        next_run_id = data.get("run_id")
        if not next_run_id:
            await self.send_error("Missing run_id")
            return

        if self.run_id and self.run_id != next_run_id:
            current_group = f"robot_run_{self.tenant_id}_{self.robot_id}_{self.run_id}"
            if current_group in self.groups:
                await self.channel_layer.group_discard(current_group, self.channel_name)
                self.groups.remove(current_group)

        self.run_id = next_run_id
        run_group = f"robot_run_{self.tenant_id}_{self.robot_id}_{self.run_id}"
        if run_group not in self.groups:
            await self.channel_layer.group_add(run_group, self.channel_name)
            self.groups.append(run_group)

        await self.send_json(
            {
                "event_type": "stream_started",
                "payload": {"run_id": self.run_id, "robot_id": self.robot_id},
            }
        )

    async def stop_streaming(self):
        if self.run_id:
            run_group = f"robot_run_{self.tenant_id}_{self.robot_id}_{self.run_id}"
            if run_group in self.groups:
                await self.channel_layer.group_discard(run_group, self.channel_name)
                self.groups.remove(run_group)
            stopped_run_id = self.run_id
            self.run_id = None
        else:
            stopped_run_id = None

        await self.send_json(
            {
                "event_type": "stream_stopped",
                "payload": {"run_id": stopped_run_id},
            }
        )

    async def on_disconnect(self, close_code):
        pass

    async def robot_event(self, event):
        await self.send_json(
            {
                "event_type": event.get("event_type"),
                "payload": event.get("payload", {}),
            }
        )
