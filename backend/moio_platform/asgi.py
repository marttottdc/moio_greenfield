"""
ASGI config for moio_platform project.

It exposes the ASGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/5.2/howto/deployment/asgi/
"""
import os

from moio_platform.env import configure_django_settings_module

# Must set DJANGO_SETTINGS_MODULE before any Django imports
configure_django_settings_module()

from channels.auth import AuthMiddlewareStack
from channels.routing import ProtocolTypeRouter, URLRouter
from channels.security.websocket import AllowedHostsOriginValidator
from django.core.asgi import get_asgi_application

django_asgi_app = get_asgi_application()

from websockets_app.routing import websocket_urlpatterns

# WebSocket: AllowedHostsOriginValidator checks Origin header against ALLOWED_HOSTS
# (e.g. Origin http://localhost:5177 → host "localhost" is allowed). Rejection happens
# before URLRouter, so no consumer runs and the client sees connection closed with no body.
application = ProtocolTypeRouter({
    "http": django_asgi_app,
    "websocket": AllowedHostsOriginValidator(
        AuthMiddlewareStack(
            URLRouter(websocket_urlpatterns)
        )
    ),
})
