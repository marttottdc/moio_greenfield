import logging
from typing import Dict, Any

from channels.db import database_sync_to_async

from websockets_app.consumers.base import TenantAwareConsumer

logger = logging.getLogger(__name__)


class CampaignStatsConsumer(TenantAwareConsumer):
    channel_prefix = "campaigns"
    
    async def setup_groups(self):
        if self.tenant_id:
            tenant_group = f"campaigns_{self.tenant_id}"
            await self.channel_layer.group_add(tenant_group, self.channel_name)
            self.groups.append(tenant_group)
    
    async def on_connect(self):
        campaign_id = self.scope['url_route']['kwargs'].get('campaign_id')
        
        if self.tenant_id and campaign_id:
            owns_campaign = await self._verify_campaign_ownership(campaign_id)
            if not owns_campaign:
                await self.send_error('Access denied to this campaign')
                await self.close(code=4003)
                return
            
            group_name = f"campaign_{self.tenant_id}_{campaign_id}"
            await self.channel_layer.group_add(group_name, self.channel_name)
            self.groups.append(group_name)
            
            await self.send_json({
                'event_type': 'connected',
                'payload': {
                    'channel': 'campaigns',
                    'campaign_id': campaign_id,
                    'tenant_id': str(self.tenant_id)
                }
            })
    
    async def campaign_stats_updated(self, event):
        await self.send_json({
            'event_type': 'stats_updated',
            'payload': event.get('payload', {}),
            'timestamp': event.get('timestamp')
        })
    
    async def campaign_status_changed(self, event):
        await self.send_json({
            'event_type': 'status_changed',
            'payload': event.get('payload', {}),
            'timestamp': event.get('timestamp')
        })
    
    async def campaign_message_sent(self, event):
        await self.send_json({
            'event_type': 'message_sent',
            'payload': event.get('payload', {}),
            'timestamp': event.get('timestamp')
        })
    
    async def campaign_message_delivered(self, event):
        await self.send_json({
            'event_type': 'message_delivered',
            'payload': event.get('payload', {}),
            'timestamp': event.get('timestamp')
        })
    
    async def campaign_message_failed(self, event):
        await self.send_json({
            'event_type': 'message_failed',
            'payload': event.get('payload', {}),
            'timestamp': event.get('timestamp')
        })
    
    async def campaign_completed(self, event):
        await self.send_json({
            'event_type': 'campaign_completed',
            'payload': event.get('payload', {}),
            'timestamp': event.get('timestamp')
        })
    
    async def on_message(self, action: str, data: Dict[str, Any]):
        if action == 'request_stats':
            await self.send_json({
                'event_type': 'stats_requested',
                'payload': {'message': 'Stats will be pushed when available'}
            })
    
    @database_sync_to_async
    def _verify_campaign_ownership(self, campaign_id: str) -> bool:
        if not self.tenant_id:
            return False
        try:
            from campaigns.models import Campaign
            with self.tenant_db_context():
                campaign = Campaign.objects.get(pk=campaign_id)
            return str(campaign.tenant_id) == str(self.tenant_id)
        except Exception:
            return False
