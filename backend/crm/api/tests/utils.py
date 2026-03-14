from __future__ import annotations

import os

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "moio_platform.test_settings")

import django  # noqa: E402

django.setup()

from django.apps import apps  # noqa: E402
from django.db import connection  # noqa: E402


def _optional_model(app_label: str, model_name: str):
    try:
        return apps.get_model(app_label, model_name)
    except LookupError:
        return None


MODELS_TO_CREATE = [
    apps.get_model("contenttypes", "ContentType"),
    apps.get_model("auth", "Permission"),
    apps.get_model("auth", "Group"),
    apps.get_model("authtoken", "Token"),
    apps.get_model("tenancy", "Tenant"),
    _optional_model("central_hub", "TenantConfiguration"),
    apps.get_model("tenancy", "MoioUser"),
    apps.get_model("tenancy", "AuthSession"),
    apps.get_model("chatbot", "AgentConfiguration"),
    apps.get_model("chatbot", "AgentSession"),
    apps.get_model("chatbot", "SessionThread"),
    apps.get_model("crm", "ContactType"),
    apps.get_model("crm", "Contact"),
    apps.get_model("crm", "Branch"),
    apps.get_model("crm", "Ticket"),
    apps.get_model("crm", "TicketComment"),
    apps.get_model("crm", "Face"),
    apps.get_model("crm", "WebhookConfig"),
]


def ensure_schema() -> None:
    existing_tables = set(connection.introspection.table_names())
    with connection.schema_editor() as schema_editor:
        for model in MODELS_TO_CREATE:
            if model is None:
                continue
            if model._meta.db_table in existing_tables:
                continue
            schema_editor.create_model(model)
            existing_tables.add(model._meta.db_table)
