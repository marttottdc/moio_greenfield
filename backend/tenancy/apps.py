from django.apps import AppConfig


class TenancyConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'tenancy'

    def ready(self):
        from django.db.models.signals import post_migrate
        from django_rls.models import enable_rls_on_migrate

        # django_rls enables policies on every post_migrate by default.
        # We keep that disabled until this codebase finishes the migration
        # away from the legacy slug-based policies.
        post_migrate.disconnect(enable_rls_on_migrate)

        import tenancy.signals  # noqa: F401
