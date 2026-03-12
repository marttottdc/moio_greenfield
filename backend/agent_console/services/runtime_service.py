from __future__ import annotations

import os
import threading
from dataclasses import replace
from pathlib import Path

from asgiref.sync import async_to_sync
from django.conf import settings

from agent_console.resolvers.django_resolvers import build_resolvers_for_backend
from agent_console.runtime.config import load_config
from agent_console.runtime.backend import AgentConsoleBackend
from agent_console.session_store_db import DatabaseSessionStore


def _api_connection_resolver(connection_name: str, *, initiator: dict | None = None) -> dict | None:
    """
    Resolve Moio platform API connection for agent tools (e.g. moio_api.run).
    Uses only Platform Configuration (Integration Hub → platform settings) my_url.
    Returns None with missingCredential if not configured, so it can be resolved in settings.
    """
    try:
        from django_tenants.utils import schema_context
        from tenancy.tenant_support import public_schema_name
        from central_hub.config import get_platform_configuration

        with schema_context(public_schema_name()):
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
        from tenancy.tenant_support import tenant_schema_context

        from central_hub.integrations.models import IntegrationConfig

        def _from_cfg(cfg) -> tuple[str | None, str | None]:
            if not cfg or not cfg.config:
                return None, None
            api_key = (cfg.config or {}).get("api_key")
            if not api_key or not str(api_key).strip():
                return None, None
            model = (cfg.config or {}).get("default_model") or "gpt-4.1-mini"
            return str(api_key).strip(), str(model).strip() or "gpt-4.1-mini"

        cfg = IntegrationConfig.get_for_tenant(tenant, "openai", "default")
        if cfg and cfg.is_configured():
            out = _from_cfg(cfg)
            if out[0]:
                return out

        schema_name = getattr(tenant, "schema_name", None)
        with tenant_schema_context(schema_name):
            qs = IntegrationConfig._base_manager.filter(tenant=tenant, slug="openai")
            for cfg in qs:
                if cfg.is_configured():
                    out = _from_cfg(cfg)
                    if out[0]:
                        return out
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


def get_runtime_backend_for_user(user, *, workspace_slug: str = "crm-agent") -> AgentConsoleBackend:
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
            integration_status_resolver=resolvers.get("integration_status_resolver"),
            integration_guidance_resolver=resolvers.get("integration_guidance_resolver"),
        )
        async_to_sync(backend.start)()
        _BACKENDS[cache_key] = backend
        return backend
