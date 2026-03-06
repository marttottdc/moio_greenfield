import json

from asgiref.sync import async_to_sync
from channels.consumer import SyncConsumer
from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncWebsocketConsumer, WebsocketConsumer
from django.template.loader import render_to_string, get_template

from chatbot.models.chatbot_session import ChatbotMemory


class ChatConsumer(AsyncWebsocketConsumer):

    async def connect(self):
        self.room_name = self.scope['url_route']['kwargs']['room_name']
        self.room_group_name = f'chat_{self.room_name}'
        self.user = self.scope["user"]

        print(f"connected to: {self.room_group_name}")

        await self.channel_layer.group_add(
            self.room_group_name,
            self.channel_name
        )
        await self.accept()

    async def disconnect(self, close_code):
        await self.channel_layer.group_discard(
            self.room_group_name,
            self.channel_name
        )
        print(f"disconnected from: {self.room_group_name}")

    async def receive(self, text_data=None, bytes_data=None):

        message = json.loads(text_data)
        # Send message to room group
        clean_msg = {
            "type": "message_handler",
            "content": message["messageInput"],
            "role": message["sender"],
            "contact": message["author"],
            "author": message["author"],
        }

        await self.channel_layer.group_send(self.room_group_name, clean_msg)

    async def chat_message(self, event):

        message = event['message']
        await self.send(text_data=json.dumps({
            'message': message
        }))

    @database_sync_to_async
    def save_message(self, room_name, message):
        print(message)
        ChatbotMemory.objects.create(room=room_name, content=message)

    async def message_handler(self, event):
        context = {
            "message": event,
            "user": self.user,
            "chat_group": self.room_group_name,
            "room_name": self.room_name,
            "contact": event["contact"]
        }
        print(context)

        html = render_to_string("chatbot/partials/new_message.html", context=context)
        await self.send(text_data=html)

    async def session_handler(self, event):
        context = {
            "message": event,
            "chat_group": self.room_group_name,
            "room_name": self.room_name,
        }

        html = render_to_string("chatbot/partials/session_update.html", context=context)
        print(html)
        await self.send(text_data=html)

# ---------------------------


class ConversationMonitor(AsyncWebsocketConsumer):

    async def connect(self):
        self.room_name = self.scope['url_route']['kwargs']
        self.room_group_name = f'conversations'

        print(f"connected to: {self.room_group_name}")

        await self.channel_layer.group_add(
            self.room_group_name,
            self.channel_name
        )
        await self.accept()

    async def disconnect(self, close_code):
        await self.channel_layer.group_discard(
            self.room_group_name,
            self.channel_name
        )
        print(f"disconnected from: {self.room_group_name}")

    async def receive(self, text_data=None, bytes_data=None):

        message = json.loads(text_data)
        # Send message to room group
        clean_msg = {
            "type": "message_handler",
            "content": message["messageInput"],
            "role": message["sender"],
            "contact": message["author"],
            "author": message["author"],
        }

        await self.channel_layer.group_send(self.room_group_name, clean_msg)

    async def session_handler(self, event):
        context = {
            "message": event,
            "chat_group": self.room_group_name,
        }

        html = render_to_string("chatbot/partials/session_update.html", context=context)
        print(html)
        await self.send(text_data=html)
