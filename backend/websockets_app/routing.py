from django.urls import re_path

from agent_console.consumers.agent_console import AgentConsoleConsumer
from websockets_app.consumers.tickets import TicketUpdatesConsumer
from websockets_app.consumers.whatsapp import WhatsAppNotificationsConsumer
from websockets_app.consumers.campaigns import CampaignStatsConsumer
from websockets_app.consumers.flow_preview import FlowPreviewConsumer
from websockets_app.consumers.desktop_crm_agent import DesktopCrmAgentConsumer
from websockets_app.consumers.shopify_storefront_chat import ShopifyStorefrontChatConsumer

websocket_urlpatterns = [
    re_path(r"^ws/agent-console/?$", AgentConsoleConsumer.as_asgi()),
    re_path(r"^ws/tickets/?$", TicketUpdatesConsumer.as_asgi()),
    re_path(r"^ws/whatsapp/?$", WhatsAppNotificationsConsumer.as_asgi()),
    re_path(r"^ws/campaigns/(?P<campaign_id>[^/]+)/?$", CampaignStatsConsumer.as_asgi()),
    re_path(r"^ws/flows/(?P<flow_id>[^/]+)/preview/stream/?$", FlowPreviewConsumer.as_asgi()),
    re_path(r"^ws/crm-agent/?$", DesktopCrmAgentConsumer.as_asgi()),
    re_path(r"^ws/shopify-chat/?$", ShopifyStorefrontChatConsumer.as_asgi()),
]
