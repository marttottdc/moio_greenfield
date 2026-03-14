"""Hypercorn dev config. Run: hypercorn -c file:hypercorn_dev.py moio_platform.asgi:application"""
import os

os.environ.setdefault("APP_ENV", "dev")

bind = [f"127.0.0.1:{os.getenv('BACKEND_PORT', '8093')}"]
worker_class = "uvloop"
workers = 1
accesslog = "-"
errorlog = "-"
loglevel = "info"
graceful_timeout = 30

# Use ext:// so streams are resolved when config is applied (picklable for worker spawn)
logconfig_dict = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "default": {
            "format": "%(asctime)s [%(process)d] [%(levelname)s] %(message)s",
            "datefmt": "%Y-%m-%d %H:%M:%S",
        },
    },
    "handlers": {
        "access_console": {
            "class": "logging.StreamHandler",
            "stream": "ext://sys.stdout",
            "formatter": "default",
        },
        "error_console": {
            "class": "logging.StreamHandler",
            "stream": "ext://sys.stderr",
            "formatter": "default",
        },
    },
    "loggers": {
        "hypercorn.access": {
            "level": "INFO",
            "handlers": ["access_console"],
            "propagate": False,
        },
        "hypercorn.error": {
            "level": "INFO",
            "handlers": ["error_console"],
            "propagate": False,
        },
    },
}

