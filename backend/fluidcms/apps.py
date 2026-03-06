from django.apps import AppConfig


class FluidcmsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    # The Python path of the application (and where Django will look for migrations)
    name = "fluidcms"
    # Keep the historical app label so existing database tables and migrations
    # that reference "landing_api" remain valid without renaming tables.
    label = "landing_api"
    verbose_name = "Fluid CMS"
