import logging
from pathlib import Path

from django.apps import AppConfig

logger = logging.getLogger(__name__)


class AgentConsoleConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "agent_console"
    label = "agent_console"
    verbose_name = "Agent Console"

    def ready(self) -> None:
        """Startup checks: ensure resources and config exist for the runtime."""
        app_dir = Path(__file__).resolve().parent
        resources_dir = app_dir / "resources"
        config_example = resources_dir / "config.example.toml"
        if not resources_dir.is_dir():
            logger.warning(
                "agent_console: resources directory not found at %s; runtime may fail to load config.",
                resources_dir,
            )
        elif not config_example.is_file():
            logger.warning(
                "agent_console: config.example.toml not found at %s; set MOIO_RUNTIME_CONFIG_PATH or add config.",
                config_example,
            )
