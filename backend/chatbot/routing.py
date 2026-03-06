from django.urls import re_path
from chatbot import consumers

websocket_urlpatterns = [
    re_path(r'ws/chatroom/(?P<room_name>[^/]+)/$', consumers.ChatConsumer.as_asgi()),
    re_path(r'ws/conversations/$', consumers.ConversationMonitor.as_asgi()),
]