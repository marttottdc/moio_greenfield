import os
import sys
import types
import uuid

import django

from django.core.management import call_command

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "moio_platform.settings")
os.environ.setdefault(
    "DATABASE_URL", f"sqlite:////tmp/flows_tests_{uuid.uuid4().hex}.sqlite3"
)


if "transformers" not in sys.modules:
    class _StubTokenizer:
        @classmethod
        def from_pretrained(cls, *args, **kwargs):
            class _Tokenizer:
                def encode(self, text):
                    return [ord(ch) for ch in text]

                def decode(self, tokens):
                    return "".join(chr(t) for t in tokens)

            return _Tokenizer()

    stub_module = types.ModuleType("transformers")
    stub_module.AutoTokenizer = _StubTokenizer
    sys.modules["transformers"] = stub_module

import pytest
from django.apps import apps
from django.db import DatabaseError, connection
from django.test import Client

if not apps.ready:
    django.setup()

_MIGRATED = False


def _ensure_migrated() -> None:
    global _MIGRATED
    if not _MIGRATED:
        try:
            call_command("migrate", run_syncdb=True, interactive=False, verbosity=0)
        except DatabaseError:
            # Some test environments disable migrations; fall back to manual creation of
            # core tables required by the flows tests.
            from django.contrib.auth.models import Group, Permission
            from django.contrib.contenttypes.models import ContentType
            from django.contrib.sessions.models import Session
            from portal.models import (
                AppConfig,
                AppMenu,
                Document,
                Instruction,
                MoioUser,
                Notification,
                Tenant,
                TenantConfiguration,
            )
            from crm.models import ContactType
            from flows.models import (
                Flow,
                FlowExecution,
                FlowGraphVersion,
                FlowScript,
                FlowScriptLog,
                FlowScriptRun,
                FlowScriptVersion,
            )

            models_to_create = [
                ContentType,
                Group,
                Permission,
                Session,
                Tenant,
                TenantConfiguration,
                MoioUser,
                Document,
                Instruction,
                Notification,
                AppConfig,
                AppMenu,
                ContactType,
                Flow,
                FlowExecution,
                FlowGraphVersion,
                FlowScript,
                FlowScriptVersion,
                FlowScriptRun,
                FlowScriptLog,
            ]

            for model in models_to_create:
                try:
                    with connection.schema_editor() as editor:
                        editor.create_model(model)
                except DatabaseError:
                    continue
        _MIGRATED = True


@pytest.fixture(scope="session", autouse=True)
def setup_django_db():
    _ensure_migrated()


@pytest.fixture
def client() -> Client:
    return Client()


@pytest.fixture
def tenant():
    from portal.models import Tenant

    tenant, _ = Tenant.objects.get_or_create(
        id=1,
        defaults={"nombre": "Acme Corp", "domain": "acme.test"},
    )
    config = tenant.configuration.first()
    if config and not config.whatsapp_name:
        config.whatsapp_name = f"tenant-{uuid.uuid4().hex[:8]}"
        config.save(update_fields=["whatsapp_name"])
    return tenant


@pytest.fixture
def flow_factory(tenant):
    from flows.models import Flow

    def factory(**overrides):
        name = overrides.pop("name", f"Test Flow {uuid.uuid4()}")
        defaults = {
            "tenant": tenant,
            "name": name,
            "description": overrides.pop("description", ""),
            "status": overrides.pop("status", "testing"),
            "is_enabled": overrides.pop("is_enabled", False),
        }
        defaults.update(overrides)
        return Flow.objects.create(**defaults)

    return factory


@pytest.fixture
def flow_script_factory(flow_factory):
    from flows.models import FlowScript

    def factory(**overrides):
        flow = overrides.pop("flow", None) or flow_factory()
        slug = overrides.pop("slug", None) or f"script-{uuid.uuid4().hex[:8]}"
        defaults = {
            "tenant": overrides.pop("tenant", flow.tenant),
            "flow": flow,
            "name": overrides.pop("name", f"Script {uuid.uuid4().hex[:6]}"),
            "slug": slug,
            "description": overrides.pop("description", ""),
        }
        defaults.update(overrides)
        return FlowScript.objects.create(**defaults)

    return factory


@pytest.fixture
def flow_script_version_factory(flow_script_factory):
    from flows.models import FlowScriptVersion

    def factory(**overrides):
        script = overrides.pop("script", None) or flow_script_factory()
        defaults = {
            "script": script,
            "tenant": overrides.pop("tenant", script.tenant),
            "flow": overrides.pop("flow", script.flow),
            "version_number": overrides.pop(
                "version_number", script.versions.count() + 1
            ),
            "code": overrides.pop("code", "print('hello world')"),
            "requirements": overrides.pop("requirements", "requests>=2.0"),
            "notes": overrides.pop("notes", ""),
        }
        defaults.update(overrides)
        return FlowScriptVersion.objects.create(**defaults)

    return factory
