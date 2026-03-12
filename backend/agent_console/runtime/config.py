from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import tomllib


DEFAULT_TOOL_ALLOWLIST = [
    "files.read",
    "files.write",
    "files.list",
    "files.search",
    "shell.run",
    "web.fetch",
    "web.request",
    "web.extract",
    "web.scrape",
    "api.run",
    "moio_api.run",
    "resource.read",
    "code.python",
    "docker.run",
    "vault.list",
    "vault.set",
    "vault.get",
    "vault.delete",
    "tools.list",
    "tools.create",
    "packages.install",
    "memory.record",
    "memory.search",
    "memory.recent",
]


RUNTIME_PACKAGE_DIR = Path(__file__).resolve().parent
DEFAULT_RUNTIME_HOME = RUNTIME_PACKAGE_DIR.parent / "resources"


def _to_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str):
        return [item.strip() for item in value.split(",") if item.strip()]
    return []


def _to_int(value: Any, fallback: int | None = None) -> int | None:
    if value is None:
        return fallback
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.strip():
        try:
            return int(value.strip())
        except ValueError:
            return fallback
    return fallback


def _to_float(value: Any, fallback: float) -> float:
    if value is None:
        return fallback
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str) and value.strip():
        try:
            return float(value.strip())
        except ValueError:
            return fallback
    return fallback


def _to_bool(value: Any, fallback: bool = False) -> bool:
    if value is None:
        return fallback
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"1", "true", "yes", "on"}:
            return True
        if normalized in {"0", "false", "no", "off"}:
            return False
    return fallback


def _to_str(value: Any, fallback: str | None = None) -> str | None:
    if value is None:
        return fallback
    text = str(value).strip()
    return text if text else fallback


@dataclass(slots=True)
class ModelConfig:
    provider: str = "openai"
    base_url: str | None = None
    api_key: str | None = None
    model: str = "gpt-4.1-mini"
    temperature: float = 0.2
    max_output_tokens: int | None = None
    timeout_seconds: float = 60.0


@dataclass(slots=True)
class SkillsConfig:
    directories: list[Path] = field(default_factory=list)
    enabled: list[str] = field(default_factory=list)
    include_in_system_prompt: bool = True
    max_skill_chars: int = 40_000


@dataclass(slots=True)
class ToolsConfig:
    allowlist: list[str] = field(default_factory=lambda: DEFAULT_TOOL_ALLOWLIST.copy())
    admin_only: list[str] = field(default_factory=list)
    workspace_root: Path = field(default_factory=lambda: Path.cwd())
    vendors_file: Path = field(default_factory=lambda: Path("./.data/vendors/vendors.json"))
    shell_enabled: bool = True
    shell_timeout_seconds: float = 30.0
    docker_enabled: bool = False
    docker_timeout_seconds: float = 60.0
    dynamic_tools_enabled: bool = True
    dynamic_tools_dir: Path = field(default_factory=lambda: Path("./.data/custom-tools"))
    package_install_enabled: bool = False
    package_install_timeout_seconds: float = 600.0
    vault_enabled: bool = True
    vault_file: Path = field(default_factory=lambda: Path("./.data/vault/secrets.enc.json"))
    vault_passphrase: str | None = None


@dataclass(slots=True)
class PluginsConfig:
    manifests_dir: Path = field(default_factory=lambda: Path("./.data/plugins"))
    additional_manifests_dirs: list[Path] = field(default_factory=list)
    platform_approved: list[str] = field(default_factory=list)
    tenant_enabled: list[str] = field(default_factory=list)
    user_allowed: list[str] = field(default_factory=list)
    approved_permissions: list[str] = field(default_factory=list)
    tenant_config_keys: list[str] = field(default_factory=list)
    user_config_keys: list[str] = field(default_factory=list)
    tenant_credentials: list[str] = field(default_factory=list)
    user_credentials: list[str] = field(default_factory=list)
    plugin_configs: dict[str, dict[str, Any]] = field(default_factory=dict)


@dataclass(slots=True)
class AgentConfig:
    session_key: str = "main"
    thinking: str | None = None
    verbosity: str = "minimal"
    timeout_ms: int | None = None
    max_steps: int = 8
    context_compaction_enabled: bool = True
    context_last_interactions: int = 3
    context_recent_messages: int = 24
    context_summary_max_chars: int = 6000
    system_prompt: str = (
        "You are a pragmatic software agent. Use available tools proactively for URLs, files, and data "
        "exploration. Do not claim you cannot access links or files when relevant tools are available. "
        "Keep replies direct and report concrete outcomes."
    )


@dataclass(slots=True)
class AppConfig:
    host: str = "127.0.0.1"
    port: int = 8088
    log_level: str = "info"


@dataclass(slots=True)
class ReplicaConfig:
    model: ModelConfig
    skills: SkillsConfig
    tools: ToolsConfig
    plugins: PluginsConfig
    agent: AgentConfig
    app: AppConfig
    sessions_dir: Path


@dataclass(slots=True)
class RuntimeConfigSource:
    config_path: Path | None
    raw: dict[str, Any]


def _runtime_home(source: RuntimeConfigSource) -> Path:
    explicit = _to_str(os.getenv("REPLICA_RUNTIME_HOME"))
    if explicit:
        return Path(explicit).expanduser().resolve()
    if source.config_path is not None:
        return source.config_path.resolve().parent
    return DEFAULT_RUNTIME_HOME.resolve()


def _resolve_path(value: str | None, *, base_dir: Path, default: Path | None = None) -> Path:
    if not value:
        return (default or base_dir).resolve()
    path = Path(value).expanduser()
    if path.is_absolute():
        return path.resolve()
    return (base_dir / path).resolve()


def _load_toml_file(path: Path | None) -> RuntimeConfigSource:
    if path is None:
        return RuntimeConfigSource(config_path=None, raw={})
    if not path.exists():
        raise FileNotFoundError(f"config file not found: {path}")
    with path.open("rb") as handle:
        loaded = tomllib.load(handle)
    if not isinstance(loaded, dict):
        raise ValueError(f"invalid config document at {path}")
    return RuntimeConfigSource(config_path=path, raw=loaded)


def load_config(explicit_path: str | None = None) -> ReplicaConfig:
    env_path = os.getenv("REPLICA_CONFIG")
    file_path = Path(explicit_path or env_path).expanduser() if (explicit_path or env_path) else None
    source = _load_toml_file(file_path)
    runtime_home = _runtime_home(source)
    repo_root = runtime_home.parent.parent if runtime_home.parent.name == "backend" else Path.cwd().resolve()

    model_raw = source.raw.get("model", {}) if isinstance(source.raw.get("model"), dict) else {}
    skills_raw = source.raw.get("skills", {}) if isinstance(source.raw.get("skills"), dict) else {}
    tools_raw = source.raw.get("tools", {}) if isinstance(source.raw.get("tools"), dict) else {}
    plugins_raw = source.raw.get("plugins", {}) if isinstance(source.raw.get("plugins"), dict) else {}
    agent_raw = source.raw.get("agent", {}) if isinstance(source.raw.get("agent"), dict) else {}
    app_raw = source.raw.get("app", {}) if isinstance(source.raw.get("app"), dict) else {}

    model_provider = _to_str(os.getenv("REPLICA_MODEL_PROVIDER"), _to_str(model_raw.get("provider")))
    model_provider = (model_provider or "openai").strip().lower()

    model_base_url = _to_str(os.getenv("REPLICA_MODEL_BASE_URL"), _to_str(model_raw.get("base_url")))
    if not model_base_url and model_provider == "xai":
        model_base_url = "https://api.x.ai/v1"

    provider_api_key = None
    if model_provider == "xai":
        provider_api_key = _to_str(os.getenv("REPLICA_MODEL_API_KEY_XAI")) or _to_str(os.getenv("XAI_API_KEY"))
    else:
        provider_api_key = _to_str(os.getenv("REPLICA_MODEL_API_KEY_OPENAI")) or _to_str(os.getenv("OPENAI_API_KEY"))

    model_api_key = (
        _to_str(os.getenv("REPLICA_MODEL_API_KEY"))
        or provider_api_key
        or _to_str(model_raw.get("api_key"))
    )
    model_name = _to_str(os.getenv("REPLICA_MODEL_NAME"), _to_str(model_raw.get("name"))) or "gpt-4.1-mini"

    model_temperature = _to_float(
        os.getenv("REPLICA_MODEL_TEMPERATURE"),
        _to_float(model_raw.get("temperature"), 0.2),
    )
    max_output_tokens = _to_int(os.getenv("REPLICA_MODEL_MAX_OUTPUT_TOKENS"), _to_int(model_raw.get("max_output_tokens")))
    model_timeout_seconds = _to_float(
        os.getenv("REPLICA_MODEL_TIMEOUT_SECONDS"),
        _to_float(model_raw.get("timeout_seconds"), 60.0),
    )

    sessions_dir = _resolve_path(
        _to_str(os.getenv("REPLICA_SESSIONS_DIR"), _to_str(source.raw.get("sessions_dir"))),
        base_dir=runtime_home,
        default=runtime_home / ".data" / "sessions",
    )

    skill_dirs = _to_list(os.getenv("REPLICA_SKILL_DIRS")) or _to_list(skills_raw.get("directories"))
    skill_enabled = _to_list(os.getenv("REPLICA_SKILLS_ENABLED")) or _to_list(skills_raw.get("enabled"))
    include_skills = _to_bool(
        os.getenv("REPLICA_INCLUDE_SKILLS_IN_PROMPT"),
        _to_bool(skills_raw.get("include_in_system_prompt"), True),
    )
    max_skill_chars = _to_int(
        os.getenv("REPLICA_MAX_SKILL_CHARS"),
        _to_int(skills_raw.get("max_skill_chars"), 40_000),
    ) or 40_000

    workspace_root = _resolve_path(
        _to_str(os.getenv("REPLICA_WORKSPACE_ROOT"), _to_str(tools_raw.get("workspace_root"))),
        base_dir=runtime_home,
        default=repo_root,
    )
    vendors_file = _resolve_path(
        _to_str(os.getenv("REPLICA_VENDORS_FILE"), _to_str(tools_raw.get("vendors_file"))),
        base_dir=runtime_home,
        default=runtime_home / ".data" / "vendors" / "vendors.json",
    )
    tool_allowlist = _to_list(os.getenv("REPLICA_TOOL_ALLOWLIST")) or _to_list(tools_raw.get("allowlist"))
    tool_admin_only = _to_list(os.getenv("REPLICA_TOOL_ADMIN_ONLY")) or _to_list(tools_raw.get("admin_only"))
    shell_enabled = _to_bool(os.getenv("REPLICA_SHELL_ENABLED"), _to_bool(tools_raw.get("shell_enabled"), True))
    shell_timeout_seconds = _to_float(
        os.getenv("REPLICA_SHELL_TIMEOUT_SECONDS"),
        _to_float(tools_raw.get("shell_timeout_seconds"), 30.0),
    )
    docker_enabled = _to_bool(
        os.getenv("REPLICA_DOCKER_ENABLED"),
        _to_bool(tools_raw.get("docker_enabled"), False),
    )
    docker_timeout_seconds = _to_float(
        os.getenv("REPLICA_DOCKER_TIMEOUT_SECONDS"),
        _to_float(tools_raw.get("docker_timeout_seconds"), 60.0),
    )
    dynamic_tools_enabled = _to_bool(
        os.getenv("REPLICA_DYNAMIC_TOOLS_ENABLED"),
        _to_bool(tools_raw.get("dynamic_tools_enabled"), True),
    )
    dynamic_tools_dir = _resolve_path(
        _to_str(os.getenv("REPLICA_DYNAMIC_TOOLS_DIR"), _to_str(tools_raw.get("dynamic_tools_dir"))),
        base_dir=runtime_home,
        default=runtime_home / ".data" / "custom-tools",
    )
    package_install_enabled = _to_bool(
        os.getenv("REPLICA_PACKAGE_INSTALL_ENABLED"),
        _to_bool(tools_raw.get("package_install_enabled"), False),
    )
    package_install_timeout_seconds = _to_float(
        os.getenv("REPLICA_PACKAGE_INSTALL_TIMEOUT_SECONDS"),
        _to_float(tools_raw.get("package_install_timeout_seconds"), 600.0),
    )
    vault_enabled = _to_bool(
        os.getenv("REPLICA_VAULT_ENABLED"),
        _to_bool(tools_raw.get("vault_enabled"), True),
    )
    vault_file = _resolve_path(
        _to_str(os.getenv("REPLICA_VAULT_FILE"), _to_str(tools_raw.get("vault_file"))),
        base_dir=runtime_home,
        default=runtime_home / ".data" / "vault" / "secrets.enc.json",
    )
    vault_passphrase = _to_str(
        os.getenv("REPLICA_VAULT_PASSPHRASE"),
        _to_str(tools_raw.get("vault_passphrase")),
    )

    plugin_manifests_dir = _resolve_path(
        _to_str(os.getenv("REPLICA_PLUGINS_DIR"), _to_str(plugins_raw.get("manifests_dir"))),
        base_dir=runtime_home,
        default=runtime_home / "plugins",
    )
    plugin_additional_manifest_dirs = [
        _resolve_path(str(entry), base_dir=runtime_home)
        for entry in (
            _to_list(os.getenv("REPLICA_PLUGINS_EXTRA_DIRS"))
            or _to_list(plugins_raw.get("additional_manifests_dirs"))
        )
        if str(entry or "").strip()
    ]
    plugin_platform_approved = _to_list(os.getenv("REPLICA_PLUGINS_PLATFORM_APPROVED")) or _to_list(
        plugins_raw.get("platform_approved")
    )
    plugin_tenant_enabled = _to_list(os.getenv("REPLICA_PLUGINS_TENANT_ENABLED")) or _to_list(
        plugins_raw.get("tenant_enabled")
    )
    plugin_user_allowed = _to_list(os.getenv("REPLICA_PLUGINS_USER_ALLOWED")) or _to_list(
        plugins_raw.get("user_allowed")
    )
    plugin_approved_permissions = _to_list(os.getenv("REPLICA_PLUGINS_APPROVED_PERMISSIONS")) or _to_list(
        plugins_raw.get("approved_permissions")
    )
    plugin_tenant_config_keys = _to_list(os.getenv("REPLICA_PLUGINS_TENANT_CONFIG_KEYS")) or _to_list(
        plugins_raw.get("tenant_config_keys")
    )
    plugin_user_config_keys = _to_list(os.getenv("REPLICA_PLUGINS_USER_CONFIG_KEYS")) or _to_list(
        plugins_raw.get("user_config_keys")
    )
    plugin_tenant_credentials = _to_list(os.getenv("REPLICA_PLUGINS_TENANT_CREDENTIALS")) or _to_list(
        plugins_raw.get("tenant_credentials")
    )
    plugin_user_credentials = _to_list(os.getenv("REPLICA_PLUGINS_USER_CREDENTIALS")) or _to_list(
        plugins_raw.get("user_credentials")
    )
    plugin_configs_raw = plugins_raw.get("plugin_configs")
    plugin_configs: dict[str, dict[str, Any]] = {}
    if isinstance(plugin_configs_raw, dict):
        for raw_plugin_id, raw_config in plugin_configs_raw.items():
            plugin_id = str(raw_plugin_id or "").strip().lower()
            if not plugin_id or not isinstance(raw_config, dict):
                continue
            plugin_configs[plugin_id] = dict(raw_config)

    session_key = (
        _to_str(os.getenv("REPLICA_SESSION_KEY"), _to_str(agent_raw.get("session_key")))
        or "main"
    )
    thinking = _to_str(os.getenv("REPLICA_THINKING"), _to_str(agent_raw.get("thinking")))
    verbosity = (
        _to_str(os.getenv("REPLICA_VERBOSITY"), _to_str(agent_raw.get("verbosity")))
        or "minimal"
    ).strip().lower()
    timeout_ms = _to_int(os.getenv("REPLICA_TIMEOUT_MS"), _to_int(agent_raw.get("timeout_ms")))
    max_steps = _to_int(os.getenv("REPLICA_MAX_STEPS"), _to_int(agent_raw.get("max_steps"), 8)) or 8
    context_compaction_enabled = _to_bool(
        os.getenv("REPLICA_CONTEXT_COMPACTION_ENABLED"),
        _to_bool(agent_raw.get("context_compaction_enabled"), True),
    )
    context_last_interactions = _to_int(
        os.getenv("REPLICA_CONTEXT_LAST_INTERACTIONS"),
        _to_int(agent_raw.get("context_last_interactions"), 3),
    ) or 3
    context_recent_messages = _to_int(
        os.getenv("REPLICA_CONTEXT_RECENT_MESSAGES"),
        _to_int(agent_raw.get("context_recent_messages"), 24),
    ) or 24
    context_summary_max_chars = _to_int(
        os.getenv("REPLICA_CONTEXT_SUMMARY_MAX_CHARS"),
        _to_int(agent_raw.get("context_summary_max_chars"), 6000),
    ) or 6000
    system_prompt = (
        _to_str(os.getenv("REPLICA_SYSTEM_PROMPT"), _to_str(agent_raw.get("system_prompt")))
        or "You are a pragmatic software agent. Use tools when needed, keep replies direct, and report concrete outcomes."
    )

    app_host = _to_str(os.getenv("REPLICA_APP_HOST"), _to_str(app_raw.get("host"))) or "127.0.0.1"
    app_port = _to_int(os.getenv("REPLICA_APP_PORT"), _to_int(app_raw.get("port"), 8088)) or 8088
    app_log_level = _to_str(os.getenv("REPLICA_APP_LOG_LEVEL"), _to_str(app_raw.get("log_level"))) or "info"

    if model_provider in {"openai", "xai"} and not model_api_key:
        raise ValueError(
            "Missing model API key. Set REPLICA_MODEL_API_KEY (or vendor-specific env vars), "
            "or configure model.api_key in config.toml."
        )

    return ReplicaConfig(
        model=ModelConfig(
            provider=model_provider,
            base_url=model_base_url,
            api_key=model_api_key,
            model=model_name,
            temperature=model_temperature,
            max_output_tokens=max_output_tokens,
            timeout_seconds=model_timeout_seconds,
        ),
        skills=SkillsConfig(
            directories=[
                _resolve_path(str(entry), base_dir=runtime_home)
                for entry in (skill_dirs or ["./skills"])
            ],
            enabled=skill_enabled,
            include_in_system_prompt=include_skills,
            max_skill_chars=max_skill_chars,
        ),
        tools=ToolsConfig(
            allowlist=tool_allowlist or DEFAULT_TOOL_ALLOWLIST.copy(),
            admin_only=tool_admin_only,
            workspace_root=workspace_root,
            vendors_file=vendors_file,
            shell_enabled=shell_enabled,
            shell_timeout_seconds=shell_timeout_seconds,
            docker_enabled=docker_enabled,
            docker_timeout_seconds=docker_timeout_seconds,
            dynamic_tools_enabled=dynamic_tools_enabled,
            dynamic_tools_dir=dynamic_tools_dir,
            package_install_enabled=package_install_enabled,
            package_install_timeout_seconds=package_install_timeout_seconds,
            vault_enabled=vault_enabled,
            vault_file=vault_file,
            vault_passphrase=vault_passphrase,
        ),
        plugins=PluginsConfig(
            manifests_dir=plugin_manifests_dir,
            additional_manifests_dirs=plugin_additional_manifest_dirs,
            platform_approved=plugin_platform_approved,
            tenant_enabled=plugin_tenant_enabled,
            user_allowed=plugin_user_allowed,
            approved_permissions=plugin_approved_permissions,
            tenant_config_keys=plugin_tenant_config_keys,
            user_config_keys=plugin_user_config_keys,
            tenant_credentials=plugin_tenant_credentials,
            user_credentials=plugin_user_credentials,
            plugin_configs=plugin_configs,
        ),
        agent=AgentConfig(
            session_key=session_key,
            thinking=thinking,
            verbosity=verbosity,
            timeout_ms=timeout_ms,
            max_steps=max_steps,
            context_compaction_enabled=context_compaction_enabled,
            context_last_interactions=context_last_interactions,
            context_recent_messages=context_recent_messages,
            context_summary_max_chars=context_summary_max_chars,
            system_prompt=system_prompt,
        ),
        app=AppConfig(host=app_host, port=app_port, log_level=app_log_level),
        sessions_dir=sessions_dir,
    )
