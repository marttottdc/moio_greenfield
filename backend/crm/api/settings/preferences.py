from __future__ import annotations

from copy import deepcopy
from typing import Any, Dict

from central_hub.models import TenantConfiguration

DEFAULT_NOTIFICATIONS: Dict[str, bool] = {
    "email": True,
    "push": True,
    "desktop": False,
}

DEFAULT_PREFERENCES: Dict[str, Any] = {
    "theme": "light",
    "language": "en",
    "timezone": "UTC",
    "notifications": DEFAULT_NOTIFICATIONS,
    "dashboard_layout": "compact",
}


def _deep_merge(base: Dict[str, Any], updates: Dict[str, Any]) -> Dict[str, Any]:
    merged: Dict[str, Any] = deepcopy(base)
    for key, value in updates.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def get_default_preferences(config: TenantConfiguration | None) -> Dict[str, Any]:
    defaults = deepcopy(DEFAULT_PREFERENCES)
    if config:
        if config.organization_timezone:
            defaults["timezone"] = config.organization_timezone
    return defaults


def build_user_preferences(user, config: TenantConfiguration | None) -> Dict[str, Any]:
    defaults = get_default_preferences(config)
    stored = user.preferences or {}
    return _deep_merge(defaults, stored)


def update_user_preferences(user, config: TenantConfiguration | None, data: Dict[str, Any]) -> Dict[str, Any]:
    existing = build_user_preferences(user, config)
    updated = _deep_merge(existing, data)
    user.preferences = updated
    user.save(update_fields=["preferences"])
    return updated
