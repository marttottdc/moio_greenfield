from django.core.cache import cache


def get_portal_configuration():

    configuration = cache.get('portal_configuration')

    if not configuration:
        from portal.models import PortalConfiguration
        configuration = PortalConfiguration.objects.first()

        # Cache the configuration for future requests (1 hour in this example)
        cache.set('portal_configuration', configuration, 60 * 60)

    return configuration

