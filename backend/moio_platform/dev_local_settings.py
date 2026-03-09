"""
Local development settings for the shared greenfield backend.

This module is intended for developer machines. It preloads a local env file,
then imports the base settings module with sane defaults for the shared dev
Postgres database and schema-based tenancy.
"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(PROJECT_ROOT / ".env.dev.local", override=True)

os.environ.setdefault("DB_HOST", "infra.moio.ai")
os.environ.setdefault("DB_PORT", "5432")
os.environ.setdefault("DB_NAME", "moio_greenfield_dev")
os.environ.setdefault("DB_USER", "greenfield_dev_admin")
os.environ.setdefault("DJANGO_TENANTS_ENABLED", "1")
os.environ.setdefault("USE_LOCAL_DEV_DEFAULTS", "0")
os.environ.setdefault("DEBUG", "true")
os.environ.setdefault("SECRET_KEY", "dev-local-unsafe-secret-key")

from .settings import *  # noqa: E402,F401,F403


DEBUG = True
ALLOWED_HOSTS = list(dict.fromkeys([*ALLOWED_HOSTS, "infra.moio.ai", "127.0.0.1", "localhost"]))
CORS_ALLOWED_ORIGINS = list(
    dict.fromkeys(
        [
            *CORS_ALLOWED_ORIGINS,
            "http://127.0.0.1:5005",
            "http://localhost:5005",
            "http://127.0.0.1:5010",
            "http://localhost:5010",
            "http://127.0.0.1:5177",
            "http://localhost:5177",
            "http://127.0.0.1:8000",
            "http://localhost:8000",
            "https://127.0.0.1:8000",
            "https://localhost:8000",
            "http://127.0.0.1:8093",
            "http://localhost:8093",
            "https://127.0.0.1:8093",
            "https://localhost:8093",
        ]
    )
)
CSRF_TRUSTED_ORIGINS = list(
    dict.fromkeys(
        [
            *CSRF_TRUSTED_ORIGINS,
            "http://127.0.0.1:8000",
            "http://localhost:8000",
            "https://127.0.0.1:8000",
            "https://localhost:8000",
            "http://127.0.0.1:8093",
            "http://localhost:8093",
            "https://127.0.0.1:8093",
            "https://localhost:8093",
            "http://127.0.0.1:5005",
            "http://localhost:5005",
            "http://127.0.0.1:5010",
            "http://localhost:5010",
            "http://127.0.0.1:5177",
            "http://localhost:5177",
        ]
    )
)
SECURE_SSL_REDIRECT = False
SESSION_COOKIE_SECURE = False
CSRF_COOKIE_SECURE = False
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SAMESITE = "Lax"
