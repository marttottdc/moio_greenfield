import logging
from typing import Dict, Any

from channels.db import database_sync_to_async

from websockets_app.consumers.base import TenantAwareConsumer

logger = logging.getLogger(__name__)


class WhatsAppNotificationsConsumer(TenantAwareConsumer):
    channel_prefix = "whatsapp"
    
    async def setup_groups(self):
        if self.tenant_id:
            group_name = f"whatsapp_{self.tenant_id}"
            await self.channel_layer.group_add(group_name, self.channel_name)
            self.groups.append(group_name)
    
    async def on_connect(self):
        if self.tenant_id:
            await self.send_json({
                'event_type': 'connected',
                'payload': {'channel': 'whatsapp', 'tenant_id': str(self.tenant_id)}
            })
    
    async def message_received(self, event):
        await self.send_json({
            'event_type': 'message_received',
            'payload': event.get('payload', {}),
            'timestamp': event.get('timestamp')
        })
    
    async def message_sent(self, event):
        await self.send_json({
            'event_type': 'message_sent',
            'payload': event.get('payload', {}),
            'timestamp': event.get('timestamp')
        })
    
    async def message_delivered(self, event):
        await self.send_json({
            'event_type': 'message_delivered',
            'payload': event.get('payload', {}),
            'timestamp': event.get('timestamp')
        })
    
    async def message_read(self, event):
        await self.send_json({
            'event_type': 'message_read',
            'payload': event.get('payload', {}),
            'timestamp': event.get('timestamp')
        })
    
    async def message_failed(self, event):
        await self.send_json({
            'event_type': 'message_failed',
            'payload': event.get('payload', {}),
            'timestamp': event.get('timestamp')
        })
    
    async def conversation_started(self, event):
        await self.send_json({
            'event_type': 'conversation_started',
            'payload': event.get('payload', {}),
            'timestamp': event.get('timestamp')
        })

    async def conversation_ended(self, event):
        await self.send_json({
            'event_type': 'conversation_ended',
            'payload': event.get('payload', {}),
            'timestamp': event.get('timestamp')
        })
    
    async def on_message(self, action: str, data: Dict[str, Any]):
        if action == 'subscribe_conversation':
            conversation_id = data.get('conversation_id')
            if conversation_id:
                owns_conversation = await self._verify_conversation_ownership(conversation_id)
                if not owns_conversation:
                    await self.send_error('Access denied to this conversation')
                    return
                
                group_name = f"whatsapp_conv_{self.tenant_id}_{conversation_id}"
                await self.channel_layer.group_add(group_name, self.channel_name)
                self.groups.append(group_name)
                await self.send_json({
                    'event_type': 'subscribed',
                    'payload': {'conversation_id': conversation_id}
                })
        
        elif action == 'unsubscribe_conversation':
            conversation_id = data.get('conversation_id')
            if conversation_id:
                group_name = f"whatsapp_conv_{self.tenant_id}_{conversation_id}"
                if group_name in self.groups:
                    await self.channel_layer.group_discard(group_name, self.channel_name)
                    self.groups.remove(group_name)
                await self.send_json({
                    'event_type': 'unsubscribed',
                    'payload': {'conversation_id': conversation_id}
                })
    
    @database_sync_to_async
    def _verify_conversation_ownership(self, conversation_id: str) -> bool:
        if not self.tenant_id:
            return False
        try:
            from chatbot.models.chatbot_session import ChatbotSession
            conversation = ChatbotSession.objects.get(session__exact=conversation_id)
            return str(conversation.tenant_id) == str(self.tenant_id)

        except Exception as e:
            logger.exception(f'Failed to verify conversation ownership {e}')
            return False
