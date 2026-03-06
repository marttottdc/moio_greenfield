"""
Portal-level Celery tasks.
This module also registers integration ingestion tasks so Celery autodiscovery picks them up.
"""

# flake8: noqa
from portal.integrations.v1.tasks import email_ingest, calendar_ingest

