from __future__ import annotations

from copy import deepcopy
from types import SimpleNamespace
from typing import Any, Dict

DEFAULT_NOTIFICATIONS: Dict[str, bool] = {
    "email": True,
    "push": True,
    "desktop": False,
}

DEFAULT_PREFERENCES: Dict[str, Any] = {
    "theme": "light",
    "language": "en",
    "timezone": "UTC",
    "currency": "USD",
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


def get_default_preferences(config: SimpleNamespace | None) -> Dict[str, Any]:
    defaults = deepcopy(DEFAULT_PREFERENCES)
    if config:
        if getattr(config, "organization_locale", ""):
            defaults["language"] = config.organization_locale
        if config.organization_timezone:
            defaults["timezone"] = config.organization_timezone
        if config.organization_currency:
            defaults["currency"] = config.organization_currency
    return defaults


def build_user_preferences(user, config: SimpleNamespace | None) -> Dict[str, Any]:
    defaults = get_default_preferences(config)
    stored = user.preferences or {}
    return _deep_merge(defaults, stored)


def _sync_profile_from_preferences(user, prefs: Dict[str, Any]) -> None:
    """Sync language/timezone to UserProfile when present in preferences."""
    try:
        profile = getattr(user, "profile", None)
        if profile is None:
            from central_hub.models import UserProfile
            profile = UserProfile.objects.filter(user=user).first()
        if profile is None:
            return
        updated = False
        if "language" in prefs and prefs["language"]:
            if profile.locale != prefs["language"]:
                profile.locale = prefs["language"]
                updated = True
        if "timezone" in prefs and prefs["timezone"]:
            if profile.timezone != prefs["timezone"]:
                profile.timezone = prefs["timezone"]
                updated = True
        if updated:
            profile.save(update_fields=["locale", "timezone"])
    except Exception:
        pass  # Avoid breaking preference save if profile sync fails


def update_user_preferences(user, config: SimpleNamespace | None, data: Dict[str, Any]) -> Dict[str, Any]:
    existing = build_user_preferences(user, config)
    updated = _deep_merge(existing, data)
    user.preferences = updated
    user.save(update_fields=["preferences"])
    _sync_profile_from_preferences(user, updated)
    return updated


def update_user_location(user, address: str) -> Dict[str, Any]:
    """Update last_location and last_location_updated_at in user.preferences (used every ~5 min)."""
    from django.utils import timezone

    stored = dict(user.preferences or {})
    stored["last_location"] = address
    stored["last_location_updated_at"] = timezone.now().isoformat()
    user.preferences = stored
    user.save(update_fields=["preferences"])
    return {"last_location": address, "last_location_updated_at": stored["last_location_updated_at"]}
