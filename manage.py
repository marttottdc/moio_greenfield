#!/usr/bin/env python
"""Compatibility wrapper that delegates to backend/manage.py."""

from pathlib import Path
import runpy
import sys


BASE_DIR = Path(__file__).resolve().parent
BACKEND_DIR = BASE_DIR / "backend"

if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

runpy.run_path(str(BACKEND_DIR / "manage.py"), run_name="__main__")
