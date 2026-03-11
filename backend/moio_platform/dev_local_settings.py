"""
Local development settings. Configuración estática para stack Docker local:
PostgreSQL vía PgBouncer (6432), Redis (6379).
Sin .env: valores fijos, siempre gana sobre variables de entorno externas.
"""

from __future__ import annotations

import os

# No load_dotenv: config estática, no depender de .env.dev.local

# Config estática: Docker local (postgres + pgbouncer + redis)
# Usar asignación directa para anular cualquier DB_* ya definido en el entorno
os.environ["DB_HOST"] = "localhost"
os.environ["DB_PORT"] = "6432"
os.environ["DB_NAME"] = "moio_greenfield"
os.environ["DB_USER"] = "moio"
os.environ["DB_PASSWORD"] = "moio_local"
os.environ["REDIS_URL"] = "redis://localhost:6379/0"
os.environ["DJANGO_TENANTS_ENABLED"] = "1"
os.environ["USE_LOCAL_DEV_DEFAULTS"] = "0"
os.environ["DEBUG"] = "true"
os.environ["SECRET_KEY"] = "dev-local-unsafe-secret-key"
# Evitar que DATABASE_URL de .env/base settings sobrescriba
os.environ.pop("DATABASE_URL", None)

from .settings import *  # noqa: E402,F401,F403

# Fuerza la config local por si .env/DATABASE_URL cargó valores remotos
DATABASES["default"] = {
    "ENGINE": "django_tenants.postgresql_backend",
    "HOST": "localhost",
    "PORT": 6432,
    "NAME": "moio_greenfield",
    "USER": "moio",
    "PASSWORD": "moio_local",
    "CONN_MAX_AGE": 0,
    "DISABLE_SERVER_SIDE_CURSORS": True,
}

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
