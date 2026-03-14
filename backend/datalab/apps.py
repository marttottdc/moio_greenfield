from django.apps import AppConfig


class DatalabConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'datalab'
    verbose_name = 'Moio Data Lab'

    def ready(self):
        """Hook para inicialización cuando la app está lista."""
        # Import core models first so ResultSet etc. are registered before analytics references them
        from datalab.core import models as core_models  # noqa: F401
        # Import other submodule models so Django discovers them under the datalab app
        from datalab.analytics import models as analytics_models  # noqa: F401
        from datalab.panels import models as panels_models  # noqa: F401
        from datalab.crm_sources import models as crm_sources_models  # noqa: F401
        from datalab.pipelines import models as pipelines_models  # noqa: F401
