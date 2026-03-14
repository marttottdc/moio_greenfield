from __future__ import absolute_import, unicode_literals

from celery import Celery
from django.conf import settings

from moio_platform.env import configure_django_settings_module

# Set the default Django settings module for Celery via APP_ENV.
configure_django_settings_module()

app = Celery('Messages')

# Using a string here means the worker doesn't have to serialize
# the configuration object to child processes.
# - namespace='CELERY' means all celery-related configuration keys
#   should have a `CELERY_` prefix.
app.config_from_object('django.conf:settings', namespace='CELERY')


# Load task modules from all registered Django app configs.
app.conf.task_default_queue = settings.APP_NAME
app.conf.beat_scheduler = 'django_celery_beat.schedulers:DatabaseScheduler'

# Ensure Celery uses Django's logging
app.conf.task_track_started = True  # Optional: track task start
app.conf.worker_hijack_root_logger = False  # Prevents Celery from overriding root logger

app.autodiscover_tasks()

# Also discover tasks in non-Django-app modules (these won't be picked up by the default
# autodiscover_tasks() which only scans INSTALLED_APPS).
# Needed for moio_platform.core.events.tasks -> task name "events.route_event".
app.autodiscover_tasks(["moio_platform.core.events"])

