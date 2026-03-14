"""
WSGI config for moio_platform project.

It exposes the WSGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/5.2/howto/deployment/wsgi/
"""

from django.core.wsgi import get_wsgi_application

from moio_platform.env import configure_django_settings_module

configure_django_settings_module()

application = get_wsgi_application()
