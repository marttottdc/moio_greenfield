from __future__ import annotations

import os
import threading
from pathlib import Path

from asgiref.sync import async_to_sync
from django.conf import settings

from moio_runtime.config import load_config
from moio_runtime.standalone_backend import StandaloneAgentBackend


_BACKENDS: dict[tuple[str, str], StandaloneAgentBackend] = {}
_LOCK = threading.Lock()


def _runtime_config_path() -> str:
    configured = str(getattr(settings, "MOIO_RUNTIME_CONFIG_PATH", "") or os.getenv("REPLICA_CONFIG") or "").strip()
    if configured:
        return configured
    return str(Path(settings.BASE_DIR) / "agent_console_runtime" / "config.example.toml")


def runtime_initiator_from_user(user) -> dict[str, object]:
    role = "admin" if getattr(user, "is_superuser", False) or getattr(user, "is_staff", False) else "member"
    return {
        "id": int(getattr(user, "id", 0) or 0),
        "email": str(getattr(user, "email", "") or "").strip().lower(),
        "displayName": str(getattr(user, "get_full_name", lambda: "")() or getattr(user, "username", "") or "").strip(),
        "tenantId": str(getattr(user, "tenant_id", "") or "").strip(),
        "tenantRole": role,
        "tenantAdmin": role == "admin",
    }


def runtime_scope_from_user(user, *, workspace_slug: str = "crm-agent") -> tuple[str, str]:
    tenant = getattr(user, "tenant", None)
    tenant_schema = str(getattr(tenant, "schema_name", "") or "").strip()
    if not tenant_schema:
        tenant_schema = str(getattr(user, "tenant_id", "") or "").strip() or "public"
    return tenant_schema, workspace_slug


def get_runtime_backend_for_user(user, *, workspace_slug: str = "crm-agent") -> StandaloneAgentBackend:
    tenant_schema, resolved_workspace = runtime_scope_from_user(user, workspace_slug=workspace_slug)
    cache_key = (tenant_schema, resolved_workspace)

    with _LOCK:
        existing = _BACKENDS.get(cache_key)
        if existing is not None:
            return existing

        config = load_config(_runtime_config_path())
        backend = StandaloneAgentBackend(
            config,
            tenant_schema=tenant_schema,
            workspace_slug=resolved_workspace,
        )
        async_to_sync(backend.start)()
        _BACKENDS[cache_key] = backend
        return backend
