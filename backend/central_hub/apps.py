# central_hub/apps.py
import os
import logging
from importlib import import_module

from django.apps import AppConfig
from django.conf import settings

logger = logging.getLogger(__name__)


class CentralHubConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'central_hub'
    label = 'central_hub'

    def ready(self):
        if os.environ.get("MOIO_SKIP_PORTAL_READY"):
            logger.debug("MOIO_SKIP_PORTAL_READY set; skipping central_hub startup hooks")
            return

        import central_hub.signals

        # Import and register handlers

        from central_hub.event_bus import event_bus
        from central_hub.events import EventTypes
        # event_bus.subscribe(EventTypes.USER_REGISTERED, send_welcome_email)

        """
        On startup:
          • Import central_hub.webhook_handlers so the hub's handlers register.
          • Import <app>.webhook_handlers for every INSTALLED_APP (if it exists),
            giving all apps the ability to drop handlers in the same way.
        """
        try:
            import_module("central_hub.webhook_handlers")
        except ModuleNotFoundError:
            logger.debug("central_hub.webhook_handlers not found (that's fine)")

        if os.environ.get("SKIP_WEBHOOK_AUTODISCOVERY") == "1":
            return

        # 2️⃣  Autodiscover other apps’ handlers
        for app in settings.INSTALLED_APPS:
            try:
                import_module(f"{app}.webhook_handlers")
            except ModuleNotFoundError:
                continue
