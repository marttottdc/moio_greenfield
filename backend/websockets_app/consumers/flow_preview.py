import logging
from typing import Optional

from channels.db import database_sync_to_async

from websockets_app.consumers.base import TenantAwareConsumer

logger = logging.getLogger(__name__)


class FlowPreviewConsumer(TenantAwareConsumer):
    """
    WebSocket consumer for flow preview streaming.
    
    Receives pushed events from the flow execution task via channel layer.
    No polling required - events are pushed directly to connected clients.
    """
    channel_prefix = "flow_preview"
    requires_auth = True

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.flow_id: Optional[str] = None
        self.run_id: Optional[str] = None

    async def connect(self):
        self.flow_id = self.scope["url_route"]["kwargs"].get("flow_id")

        if not self.flow_id:
            await self.close(code=4000)
            return

        await super().connect()

    async def setup_groups(self):
        if self.tenant_id and self.flow_id:
            group_name = f"flow_preview_{self.tenant_id}_{self.flow_id}"
            await self.channel_layer.group_add(group_name, self.channel_name)
            self.groups.append(group_name)

    async def on_connect(self):
        await self.send_json({
            "event_type": "connected",
            "payload": {"flow_id": self.flow_id}
        })

    async def on_message(self, action: str, data: dict):
        if action == "start_stream":
            await self.start_streaming(data)
        elif action == "stop_stream":
            await self.stop_streaming()

    async def start_streaming(self, data: dict):
        self.run_id = data.get("run_id")
        if not self.run_id:
            await self.send_error("Missing run_id")
            return

        run_group = f"flow_preview_{self.tenant_id}_{self.flow_id}_{self.run_id}"
        if run_group not in self.groups:
            await self.channel_layer.group_add(run_group, self.channel_name)
            self.groups.append(run_group)

        await self.send_json({
            "event_type": "stream_started",
            "payload": {"run_id": self.run_id, "flow_id": self.flow_id}
        })

    async def stop_streaming(self):
        if self.run_id:
            run_group = f"flow_preview_{self.tenant_id}_{self.flow_id}_{self.run_id}"
            if run_group in self.groups:
                await self.channel_layer.group_discard(run_group, self.channel_name)
                self.groups.remove(run_group)

        await self.send_json({
            "event_type": "stream_stopped",
            "payload": {"run_id": self.run_id}
        })

    async def on_disconnect(self, close_code):
        pass

    async def preview_event(self, event):
        """
        Handler for preview events pushed from the flow execution task.
        This is called when WebSocketEventPublisher.publish_flow_preview_event() is invoked.
        """
        await self.send_json({
            "event_type": event.get("event_type"),
            "payload": event.get("payload", {})
        })

    @database_sync_to_async
    def _get_execution(self):
        from flows.models import FlowExecution, Flow
        try:
            flow = Flow.objects.get(id=self.flow_id)
            return (
                FlowExecution.objects.filter(
                    flow=flow,
                    execution_context__preview_run_id=self.run_id
                )
                .order_by("-started_at")
                .first()
            )
        except Flow.DoesNotExist:
            return None
