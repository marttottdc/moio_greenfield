"""Environment helpers for selecting the Django settings module."""
from __future__ import annotations

import os


APP_ENV_TO_SETTINGS = {
    "prod": "moio_platform.settings",
    "production": "moio_platform.settings",
    "dev": "moio_platform.dev_local_settings",
    "development": "moio_platform.dev_local_settings",
    "local": "moio_platform.dev_local_settings",
    "test": "moio_platform.test_settings",
    "testing": "moio_platform.test_settings",
}


def get_django_settings_module() -> str:
    """
    Resolve the Django settings module from APP_ENV.

    Rules:
    - Respect an explicit DJANGO_SETTINGS_MODULE if already provided.
    - APP_ENV=prod|production -> moio_platform.settings
    - APP_ENV=dev|development|local -> moio_platform.dev_local_settings
    - APP_ENV=test|testing -> moio_platform.test_settings
    - Missing or unknown APP_ENV defaults to production settings.
    """
    explicit = os.getenv("DJANGO_SETTINGS_MODULE")
    if explicit:
        return explicit

    app_env = str(os.getenv("APP_ENV", "prod") or "prod").strip().lower()
    return APP_ENV_TO_SETTINGS.get(app_env, "moio_platform.settings")


def configure_django_settings_module() -> str:
    """Set DJANGO_SETTINGS_MODULE if needed and return the final value."""
    settings_module = get_django_settings_module()
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", settings_module)
    return settings_module
