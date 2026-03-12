from __future__ import annotations

"""Runtime entrypoint bound to the active Django backend."""

import os
import sys

from moio_platform.asgi import application

app = application


def main() -> None:
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "moio_platform.settings")
    from django.core.management import execute_from_command_line

    argv = sys.argv[1:] or ["runserver", "127.0.0.1:8000"]
    execute_from_command_line(["manage.py", *argv])
