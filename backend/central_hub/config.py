from django.core.cache import cache


def get_platform_configuration():
    configuration = cache.get('platform_configuration')
    if not configuration:
        from central_hub.models import PlatformConfiguration
        configuration = PlatformConfiguration.objects.first()
        cache.set('platform_configuration', configuration, 60 * 60)
    return configuration


def get_portal_configuration():
    """Backward compatibility alias."""
    return get_platform_configuration()


def get_platform_configuration_for_public_request():
    """
    Load PlatformConfiguration for unauthenticated/public requests (e.g. Shopify embed bootstrap, webhooks).
    Uses base manager; no cache. Single-schema mode (no tenant schema switching).
    """
    from central_hub.models import PlatformConfiguration
    return PlatformConfiguration._base_manager.first()

