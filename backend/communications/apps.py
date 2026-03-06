from django.apps import AppConfig


class CommunicationsConfig(AppConfig):
    """
    Communications app configuration.

    This app handles multi-channel communication with AI integration.
    Supports WhatsApp, Email, Instagram, Messenger, Web, and Desktop channels.
    """
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'communications'
    verbose_name = 'Communications'

    def ready(self):
        # Import signals to register them
        from . import signals