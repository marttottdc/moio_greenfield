"""Hypercorn dev config. Run: hypercorn -c file:hypercorn_dev.py moio_platform.asgi:application"""
import os
from pathlib import Path

# Ensure dev_local_settings when .env.dev.local exists (Postgres + tenants)
_root = Path(__file__).resolve().parent.parent
if (_root / ".env.dev.local").exists():
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "moio_platform.dev_local_settings")

bind = [f"0.0.0.0:{os.getenv('BACKEND_PORT', '8093')}"]
worker_class = "uvloop"
workers = 1
accesslog = "-"
errorlog = "-"
loglevel = "debug"
graceful_timeout = 30

