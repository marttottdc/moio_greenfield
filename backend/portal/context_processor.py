from portal.config import get_portal_configuration
from django.conf import settings


def site_configuration(request):
    try:
        site_configuration = get_portal_configuration()
        #page_title = site_configuration.site_name
        #main_logo = site_configuration.logo

    except Exception as e:
        site_configuration = {"page_title": "Sin Configurar",
                              "main_logo": "empty"}

    return {'site_configuration': site_configuration, 'system_version': settings.APP_VERSION}

