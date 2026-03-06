"""
Provider registry: resolve provider by name from settings.
Credentials live in config / tenant secret store; only used at call time.
"""
import logging
from typing import Any, Dict, Optional

from django.conf import settings
from integration_hub.providers.base import APIProvider, RequestContext

logger = logging.getLogger(__name__)


def get_provider(name: str, context: Optional[RequestContext] = None) -> APIProvider:
    """Return the configured provider instance for the given name."""
    config = _get_hub_config()
    providers_config = config.get("providers", {})
    if name not in providers_config:
        raise ValueError(f"Unknown provider: {name}. Available: {list(providers_config.keys())}")

    provider_config = providers_config[name]
    if name == "moio":
        from integration_hub.providers.moio import MoioProvider
        return MoioProvider(config=provider_config)
    # Future: hubspot, stripe, google_places, etc.
    raise ValueError(f"Provider not implemented: {name}")


def _get_hub_config() -> Dict[str, Any]:
    return getattr(settings, "INTEGRATION_HUB", {})
