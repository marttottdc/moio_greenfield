from __future__ import annotations

import os
import threading
from dataclasses import replace
from pathlib import Path
from typing import Any, Mapping
from urllib.parse import urlparse

from asgiref.sync import async_to_sync
from django.conf import settings

from agent_console.resolvers.django_resolvers import build_resolvers_for_backend
from agent_console.runtime.config import load_config
from agent_console.runtime.backend import AgentConsoleBackend
from agent_console.session_store_db import DatabaseSessionStore
from tenancy.resolution import resolve_tenant_from_user


def _normalize_runtime_base_url(value: Any) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    parsed = urlparse(raw)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return ""
    return f"{parsed.scheme}://{parsed.netloc}".rstrip("/")


def runtime_base_url_from_request(request) -> str:
    try:
        return _normalize_runtime_base_url(request.build_absolute_uri("/"))
    except Exception:
        return ""


def runtime_base_url_from_scope(scope: Mapping[str, Any] | None) -> str:
    if not isinstance(scope, Mapping):
        return ""
    headers_raw = scope.get("headers") or []
    headers: dict[str, str] = {}
    for key, value in headers_raw:
        try:
            headers[key.decode("latin1").strip().lower()] = value.decode("latin1").strip()
        except Exception:
            continue
    host = headers.get("x-forwarded-host") or headers.get("host") or ""
    proto = headers.get("x-forwarded-proto") or str(scope.get("scheme") or "").strip().lower()
    if "," in host:
        host = host.split(",", 1)[0].strip()
    if "," in proto:
        proto = proto.split(",", 1)[0].strip().lower()
    if proto in {"ws", "http"}:
        proto = "http"
    elif proto in {"wss", "https"}:
        proto = "https"
    else:
        proto = "https"
    return _normalize_runtime_base_url(f"{proto}://{host}") if host else ""


def _api_connection_resolver(connection_name: str, *, initiator: dict | None = None) -> dict | None:
    """
    Resolve Moio platform API connection for agent tools (e.g. moio_api.run).
    Prefers the live runtime origin when present on the initiator and otherwise
    falls back to Platform Configuration (Integration Hub → platform settings) my_url.
    """
    runtime_base_url = _normalize_runtime_base_url((initiator or {}).get("runtimeBaseUrl"))
    if runtime_base_url:
        return {
            "baseUrl": runtime_base_url,
            "authType": "initiator_bearer",
            "source": "internal_api",
            "protocol": "rest",
        }
    try:
        from tenancy.tenant_support import public_schema_name, public_schema_context
        from central_hub.config import get_platform_configuration

        with public_schema_context(public_schema_name()):
            cfg = get_platform_configuration()
            if not cfg:
                return {
                    "missingCredential": True,
                    "missingCredentialReason": "platform_url_not_configured",
                    "message": "Platform URL is not configured. Set it in Platform Admin → Integration Hub → platform settings (my_url).",
                }
            base_url = (getattr(cfg, "my_url", None) or "").strip().rstrip("/")
            if not base_url:
                return {
                    "missingCredential": True,
                    "missingCredentialReason": "platform_url_empty",
                    "message": "Platform URL (my_url) is empty. Set it in Platform Admin → Integration Hub → platform settings.",
                }
            return {
                "baseUrl": base_url,
                "authType": "initiator_bearer",
                "source": "internal_api",
                "protocol": "rest",
            }
    except Exception as e:
        return {
            "missingCredential": True,
            "missingCredentialReason": "platform_url_error",
            "message": f"Could not load platform URL: {e}. Configure it in Platform Admin → Integration Hub → platform settings.",
        }


_BACKENDS: dict[tuple[str, str], AgentConsoleBackend] = {}
_LOCK = threading.Lock()


class OpenAINotConfiguredError(ValueError):
    """Raised when the tenant has no OpenAI IntegrationConfig configured."""

    MESSAGE = (
        "OpenAI integration is not configured for this tenant. "
        "Configure it in Settings → Integrations → OpenAI."
    )


class TenantRequiredError(ValueError):
    """Raised when a user without tenant tries to access tenant runtime."""

    MESSAGE = "Agent console requires a tenant-bound user. Please choose a tenant session first."


def _get_tenant_openai_config(user) -> tuple[str | None, str | None]:
    """
    Load OpenAI api_key and default_model from IntegrationConfig for the user's tenant.
    Returns (api_key, default_model) or (None, None) if not configured.
    No env fallback: only tenant IntegrationConfig is used.
    """
    tenant = getattr(user, "tenant", None)
    if not tenant:
        return None, None
    try:
        from tenancy.tenant_support import tenant_rls_context

        from central_hub.integrations.models import IntegrationConfig

        def _from_cfg(cfg) -> tuple[str | None, str | None]:
            if not cfg or not cfg.config:
                return None, None
            api_key = (cfg.config or {}).get("api_key")
            if not api_key or not str(api_key).strip():
                return None, None
            # Do not use masked value (sk-****) sent from frontend
            if isinstance(api_key, str) and "****" in api_key:
                return None, None
            model = (cfg.config or {}).get("default_model") or "gpt-4.1-mini"
            return str(api_key).strip(), str(model).strip() or "gpt-4.1-mini"

        cfg = IntegrationConfig.get_for_tenant(tenant, "openai", "default")
        if cfg and cfg.is_configured():
            out = _from_cfg(cfg)
            if out[0]:
                return out

        schema_name = getattr(tenant, "schema_name", None)
        with tenant_rls_context(schema_name):
            qs = IntegrationConfig._base_manager.filter(tenant=tenant, slug="openai")
            for cfg in qs:
                if cfg.is_configured():
                    out = _from_cfg(cfg)
                    if out[0]:
                        return out
        # If not found, row may have tenant_uuid NULL (RLS hides it). Run: python manage.py backfill_tenant_uuid
    except Exception:
        pass
    return None, None


def _runtime_config_path() -> str:
    configured = str(getattr(settings, "MOIO_RUNTIME_CONFIG_PATH", "") or os.getenv("REPLICA_CONFIG") or "").strip()
    if configured:
        return configured
    # Default: agent_console/resources/config.example.toml
    app_dir = Path(__file__).resolve().parent.parent
    return str(app_dir / "resources" / "config.example.toml")


def runtime_initiator_from_user(user, *, base_url: str | None = None) -> dict[str, object]:
    role = "admin" if getattr(user, "is_superuser", False) or getattr(user, "is_staff", False) else "member"
    initiator = {
        "id": int(getattr(user, "id", 0) or 0),
        "email": str(getattr(user, "email", "") or "").strip().lower(),
        "displayName": str(getattr(user, "get_full_name", lambda: "")() or getattr(user, "username", "") or "").strip(),
        "tenantId": str(getattr(user, "tenant_id", "") or "").strip(),
        "tenantRole": role,
        "tenantAdmin": role == "admin",
    }
    normalized_base_url = _normalize_runtime_base_url(base_url)
    if normalized_base_url:
        initiator["runtimeBaseUrl"] = normalized_base_url
    return initiator


def runtime_scope_from_user(user, *, workspace_slug: str = "main") -> tuple[str, str]:
    tenant = resolve_tenant_from_user(user) or getattr(user, "tenant", None)
    if not tenant:
        tenant_id = getattr(user, "tenant_id", None)
        if tenant_id:
            from tenancy.tenant_support import public_schema_name, public_schema_context
            with public_schema_context(public_schema_name()):
                from tenancy.models import Tenant
                tenant = Tenant.objects.filter(pk=tenant_id).first()
    if not tenant:
        raise TenantRequiredError(TenantRequiredError.MESSAGE)
    # Use schema_name for scope; fall back to subdomain (rls_slug) when schema_name is empty
    tenant_schema = str(getattr(tenant, "schema_name", "") or "").strip()
    if not tenant_schema:
        tenant_schema = str(getattr(tenant, "subdomain", "") or getattr(tenant, "rls_slug", "") or "").strip()
    if not tenant_schema:
        raise TenantRequiredError(TenantRequiredError.MESSAGE)
    return tenant_schema, workspace_slug


def get_runtime_backend_for_user(user, *, workspace_slug: str = "main") -> AgentConsoleBackend:
    if getattr(user, "tenant_id", None) in (None, ""):
        raise TenantRequiredError(TenantRequiredError.MESSAGE)
    tenant_schema, resolved_workspace = runtime_scope_from_user(user, workspace_slug=workspace_slug)
    cache_key = (tenant_schema, resolved_workspace)

    with _LOCK:
        existing = _BACKENDS.get(cache_key)
        if existing is not None:
            return existing

        # Use only tenant OpenAI config (IntegrationConfig); no env fallback
        tenant_api_key, tenant_model = _get_tenant_openai_config(user)
        if getattr(user, "tenant", None) and not tenant_api_key:
            raise OpenAINotConfiguredError(OpenAINotConfiguredError.MESSAGE)
        runtime_config_path = _runtime_config_path()
        previous_model_api_key = os.environ.get("REPLICA_MODEL_API_KEY")
        try:
            if tenant_api_key:
                os.environ["REPLICA_MODEL_API_KEY"] = str(tenant_api_key).strip()
            config = load_config(runtime_config_path)
        except ValueError as exc:
            if "Missing model API key" in str(exc):
                raise OpenAINotConfiguredError(OpenAINotConfiguredError.MESSAGE) from exc
            raise
        finally:
            if tenant_api_key:
                if previous_model_api_key is None:
                    os.environ.pop("REPLICA_MODEL_API_KEY", None)
                else:
                    os.environ["REPLICA_MODEL_API_KEY"] = previous_model_api_key

        config = replace(
            config,
            model=replace(
                config.model,
                api_key=tenant_api_key,
                model=(tenant_model or config.model.model) if tenant_api_key else config.model.model,
            ),
        )
        # Sessions in DB per tenant/workspace; no file-based sessions_dir
        session_store = DatabaseSessionStore(tenant_schema=tenant_schema, workspace_slug=resolved_workspace)

        resolvers = build_resolvers_for_backend(tenant_schema, resolved_workspace)
        backend = AgentConsoleBackend(
            config,
            tenant_schema=tenant_schema,
            workspace_slug=resolved_workspace,
            session_store=session_store,
            api_connection_resolver=_api_connection_resolver,
            workspace_profile_resolver=resolvers.get("workspace_profile_resolver"),
            workspace_skills_resolver=resolvers.get("workspace_skills_resolver"),
            agent_profile_state_resolver=resolvers.get("agent_profile_state_resolver"),
            agent_profiles_catalog_resolver=resolvers.get("agent_profiles_catalog_resolver"),
            agent_profile_upsert_handler=resolvers.get("agent_profile_upsert_handler"),
            plugin_user_allowlist_resolver=resolvers.get("plugin_user_allowlist_resolver"),
            plugin_runtime_config_resolver=resolvers.get("plugin_runtime_config_resolver"),
            installed_plugins_resolver=resolvers.get("installed_plugins_resolver"),
            integration_status_resolver=resolvers.get("integration_status_resolver"),
            integration_guidance_resolver=resolvers.get("integration_guidance_resolver"),
        )
        async_to_sync(backend.start)()
        _BACKENDS[cache_key] = backend
        return backend


def invalidate_runtime_backend_cache(*, tenant_schema: str | None = None, workspace_slug: str | None = None) -> int:
    """Invalidate cached runtime backends by tenant/workspace scope."""
    removed: list[AgentConsoleBackend] = []
    with _LOCK:
        keys = list(_BACKENDS.keys())
        for key in keys:
            scope_tenant, scope_workspace = key
            if tenant_schema and scope_tenant != tenant_schema:
                continue
            if workspace_slug and scope_workspace != workspace_slug:
                continue
            backend = _BACKENDS.pop(key, None)
            if backend is not None:
                removed.append(backend)
    for backend in removed:
        try:
            async_to_sync(backend.stop)()
        except Exception:
            continue
    return len(removed)
