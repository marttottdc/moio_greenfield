from django.apps import AppConfig


class DatalabConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'datalab'
    verbose_name = 'Moio Data Lab'

    def ready(self):
        """Hook para inicialización cuando la app está lista."""
        # Import analytics models so Django discovers them as part of datalab app
        from datalab.analytics import models as analytics_models  # noqa: F401
        
        # Importar señales si es necesario
        # from . import signals
