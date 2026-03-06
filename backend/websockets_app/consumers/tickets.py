import logging
from typing import Dict, Any

from channels.db import database_sync_to_async

from websockets_app.consumers.base import TenantAwareConsumer

logger = logging.getLogger(__name__)


class TicketUpdatesConsumer(TenantAwareConsumer):
    channel_prefix = "tickets"
    
    async def setup_groups(self):
        if self.tenant_id:
            group_name = f"tickets_{self.tenant_id}"
            await self.channel_layer.group_add(group_name, self.channel_name)
            self.groups.append(group_name)
    
    async def on_connect(self):
        if self.tenant_id:
            await self.send_json({
                'event_type': 'connected',
                'payload': {'channel': 'tickets', 'tenant_id': str(self.tenant_id)}
            })
    
    async def ticket_created(self, event):
        await self.send_json({
            'event_type': 'ticket_created',
            'payload': event.get('payload', {}),
            'timestamp': event.get('timestamp')
        })
    
    async def ticket_updated(self, event):
        await self.send_json({
            'event_type': 'ticket_updated',
            'payload': event.get('payload', {}),
            'timestamp': event.get('timestamp')
        })
    
    async def ticket_status_changed(self, event):
        await self.send_json({
            'event_type': 'ticket_status_changed',
            'payload': event.get('payload', {}),
            'timestamp': event.get('timestamp')
        })
    
    async def ticket_assigned(self, event):
        await self.send_json({
            'event_type': 'ticket_assigned',
            'payload': event.get('payload', {}),
            'timestamp': event.get('timestamp')
        })
    
    async def ticket_comment_added(self, event):
        await self.send_json({
            'event_type': 'ticket_comment_added',
            'payload': event.get('payload', {}),
            'timestamp': event.get('timestamp')
        })
    
    async def on_message(self, action: str, data: Dict[str, Any]):
        if action == 'subscribe_ticket':
            ticket_id = data.get('ticket_id')
            if ticket_id:
                owns_ticket = await self._verify_ticket_ownership(ticket_id)
                if not owns_ticket:
                    await self.send_error('Access denied to this ticket')
                    return
                
                group_name = f"ticket_{self.tenant_id}_{ticket_id}"
                await self.channel_layer.group_add(group_name, self.channel_name)
                self.groups.append(group_name)
                await self.send_json({
                    'event_type': 'subscribed',
                    'payload': {'ticket_id': ticket_id}
                })
        
        elif action == 'unsubscribe_ticket':
            ticket_id = data.get('ticket_id')
            if ticket_id:
                group_name = f"ticket_{self.tenant_id}_{ticket_id}"
                if group_name in self.groups:
                    await self.channel_layer.group_discard(group_name, self.channel_name)
                    self.groups.remove(group_name)
                await self.send_json({
                    'event_type': 'unsubscribed',
                    'payload': {'ticket_id': ticket_id}
                })
    
    @database_sync_to_async
    def _verify_ticket_ownership(self, ticket_id: str) -> bool:
        if not self.tenant_id:
            return False
        try:
            from crm.models import Ticket
            ticket = Ticket.objects.get(pk=ticket_id)
            return str(ticket.tenant_id) == str(self.tenant_id)
        except Exception:
            return False
