"""
ASGI config for moio_platform project.

It exposes the ASGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/5.2/howto/deployment/asgi/
"""

import os
from pathlib import Path

from channels.auth import AuthMiddlewareStack
from channels.routing import ProtocolTypeRouter, URLRouter
from channels.security.websocket import AllowedHostsOriginValidator
from django.core.asgi import get_asgi_application

# Use dev_local_settings when .env.dev.local exists (Postgres + tenants)
_project_root = Path(__file__).resolve().parents[2]
if (Path(_project_root) / ".env.dev.local").exists():
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "moio_platform.dev_local_settings")
else:
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "moio_platform.settings")

django_asgi_app = get_asgi_application()

from websockets_app.routing import websocket_urlpatterns

application = ProtocolTypeRouter({
    "http": django_asgi_app,
    "websocket": AllowedHostsOriginValidator(
        AuthMiddlewareStack(
            URLRouter(websocket_urlpatterns)
        )
    ),
})
