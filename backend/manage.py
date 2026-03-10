#!/usr/bin/env python
"""Django's command-line utility for administrative tasks."""
import os
import sys
from pathlib import Path


def main():
    """Run administrative tasks."""
    project_root = Path(__file__).resolve().parents[1]
    if (project_root.parent / ".env.dev.local").exists():
        os.environ.setdefault("DJANGO_SETTINGS_MODULE", "moio_platform.dev_local_settings")
    else:
        os.environ.setdefault("DJANGO_SETTINGS_MODULE", "moio_platform.settings")
    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc:
        raise ImportError(
            "Couldn't import Django. Are you sure it's installed and "
            "available on your PYTHONPATH environment variable? Did you "
            "forget to activate a virtual environment?"
        ) from exc
    execute_from_command_line(sys.argv)


if __name__ == '__main__':
    main()
