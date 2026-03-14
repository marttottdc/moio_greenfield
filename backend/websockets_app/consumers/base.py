import json
import logging
from typing import Optional, Dict, Any
from dataclasses import dataclass, asdict
from datetime import datetime
from contextlib import contextmanager

from channels.generic.websocket import AsyncJsonWebsocketConsumer
from channels.db import database_sync_to_async
from django.contrib.auth import get_user_model
from rest_framework_simplejwt.tokens import AccessToken
from rest_framework_simplejwt.exceptions import TokenError

logger = logging.getLogger(__name__)
User = get_user_model()


@dataclass
class WebSocketEvent:
    event_type: str
    payload: Dict[str, Any]
    timestamp: Optional[str] = None
    
    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.utcnow().isoformat()
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class TenantAwareConsumer(AsyncJsonWebsocketConsumer):
    requires_auth: bool = True
    channel_prefix: str = "default"
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = None
        self.tenant = None
        self.tenant_id = None
        self.tenant_schema = None
        self.groups = []

    @contextmanager
    def tenant_db_context(self, *, use_public: bool = False):
        from tenancy.tenant_support import tenant_rls_context, public_schema_name

        schema_name = public_schema_name() if use_public else (self.tenant_schema or None)
        with tenant_rls_context(schema_name):
            yield
    
    async def connect(self):
        if self.requires_auth:
            authenticated = await self.authenticate()
            if not authenticated:
                await self.close(code=4001)
                return
        
        await self.accept()
        await self.setup_groups()
        await self.on_connect()
        
        logger.info(f"WebSocket connected: user={self.user}, tenant={self.tenant_id}")
    
    async def disconnect(self, close_code):
        for group_name in self.groups:
            await self.channel_layer.group_discard(group_name, self.channel_name)
        
        await self.on_disconnect(close_code)
        logger.info(f"WebSocket disconnected: user={self.user}, code={close_code}")
    
    async def receive_json(self, content, **kwargs):
        action = content.get('action')
        data = content.get('data', {})
        
        if action == 'authenticate':
            await self.handle_authentication(data)
        elif action == 'subscribe':
            await self.handle_subscribe(data)
        elif action == 'unsubscribe':
            await self.handle_unsubscribe(data)
        else:
            await self.on_message(action, data)
    
    async def authenticate(self) -> bool:
        token = None
        
        query_string = self.scope.get('query_string', b'').decode()
        if query_string:
            params = dict(param.split('=') for param in query_string.split('&') if '=' in param)
            token = params.get('token')
        
        if not token:
            headers = dict(self.scope.get('headers', []))
            auth_header = headers.get(b'authorization', b'').decode()
            if auth_header.startswith('Bearer '):
                token = auth_header[7:]
        
        if not token:
            return False
        
        try:
            access_token = AccessToken(token)
            user_id = access_token.get('user_id')
            self.tenant_id = access_token.get('tenant_id')
            self.tenant_schema = access_token.get('tenant_schema')

            self.user = await self.get_user(user_id)
            if self.user is None:
                return False
            
            self.scope['user'] = self.user
            self.scope['tenant'] = None

            if self.tenant_id:
                self.tenant = await self.get_tenant(self.tenant_id, self.tenant_schema)
                if self.tenant is None:
                    logger.warning(f"Tenant {self.tenant_id} not found")
                    return False
                if not self.tenant_schema:
                    self.tenant_schema = getattr(self.tenant, "schema_name", None)
                self.scope['tenant'] = self.tenant

            return True
            
        except TokenError as e:
            logger.warning(f"JWT authentication failed: {e}")
            return False
        except Exception as e:
            logger.error(f"Authentication error: {e}")
            return False
    
    async def handle_authentication(self, data: Dict[str, Any]):
        token = data.get('token')
        if not token:
            await self.send_error('Missing token')
            return
        
        try:
            access_token = AccessToken(token)
            user_id = access_token.get('user_id')
            self.tenant_id = access_token.get('tenant_id')
            self.tenant_schema = access_token.get('tenant_schema')

            self.user = await self.get_user(user_id)
            if self.user:
                self.scope['user'] = self.user
                if self.tenant_id:
                    self.tenant = await self.get_tenant(self.tenant_id, self.tenant_schema)
                    if self.tenant and not self.tenant_schema:
                        self.tenant_schema = getattr(self.tenant, "schema_name", None)
                    self.scope['tenant'] = self.tenant
                await self.setup_groups()
                await self.send_json({
                    'event_type': 'authenticated',
                    'payload': {'success': True, 'user_id': str(user_id)}
                })
            else:
                await self.send_error('User not found')
                
        except TokenError as e:
            await self.send_error(f'Invalid token: {str(e)}')
    
    async def handle_subscribe(self, data: Dict[str, Any]):
        channel = data.get('channel')
        if not channel:
            await self.send_error('Missing channel')
            return
        
        group_name = self.get_tenant_group_name(channel)
        if group_name not in self.groups:
            await self.channel_layer.group_add(group_name, self.channel_name)
            self.groups.append(group_name)
        
        await self.send_json({
            'event_type': 'subscribed',
            'payload': {'channel': channel}
        })
    
    async def handle_unsubscribe(self, data: Dict[str, Any]):
        channel = data.get('channel')
        if not channel:
            await self.send_error('Missing channel')
            return
        
        group_name = self.get_tenant_group_name(channel)
        if group_name in self.groups:
            await self.channel_layer.group_discard(group_name, self.channel_name)
            self.groups.remove(group_name)
        
        await self.send_json({
            'event_type': 'unsubscribed',
            'payload': {'channel': channel}
        })
    
    def get_tenant_group_name(self, channel: str) -> str:
        tenant_scope = self.tenant_schema or self.tenant_id
        if tenant_scope:
            return f"{self.channel_prefix}_{tenant_scope}_{channel}"
        return f"{self.channel_prefix}_{channel}"
    
    async def setup_groups(self):
        pass
    
    async def broadcast_event(self, event: WebSocketEvent):
        await self.send_json(event.to_dict())
    
    async def send_error(self, message: str, code: Optional[str] = None):
        await self.send_json({
            'event_type': 'error',
            'payload': {'message': message, 'code': code}
        })
    
    async def event_handler(self, event):
        await self.send_json({
            'event_type': event.get('event_type'),
            'payload': event.get('payload', {}),
            'timestamp': event.get('timestamp', datetime.utcnow().isoformat())
        })
    
    async def on_connect(self):
        pass
    
    async def on_disconnect(self, close_code):
        pass
    
    async def on_message(self, action: str, data: Dict[str, Any]):
        pass
    
    @database_sync_to_async
    def get_user(self, user_id):
        try:
            with self.tenant_db_context(use_public=True):
                return User.objects.get(pk=user_id)
        except User.DoesNotExist:
            return None
    
    @database_sync_to_async
    def get_tenant(self, tenant_id, tenant_schema=None):
        from central_hub.models import Tenant
        try:
            with self.tenant_db_context(use_public=True):
                if tenant_schema:
                    tenant = Tenant.objects.filter(schema_name=tenant_schema).first()
                    if tenant is not None:
                        return tenant
                return Tenant.objects.get(pk=tenant_id)
        except Tenant.DoesNotExist:
            return None
    
    async def verify_resource_ownership(self, model_class, resource_id: str) -> bool:
        return await self._check_ownership(model_class, resource_id)
    
    @database_sync_to_async
    def _check_ownership(self, model_class, resource_id: str) -> bool:
        if not self.tenant_id:
            return False
        try:
            with self.tenant_db_context():
                obj = model_class.objects.get(pk=resource_id)
            if hasattr(obj, 'tenant_id'):
                return str(obj.tenant_id) == str(self.tenant_id)
            if hasattr(obj, 'tenant'):
                return str(obj.tenant.id) == str(self.tenant_id)
            return True
        except model_class.DoesNotExist:
            return False
