"""Hypercorn dev config. Run: hypercorn -c file:hypercorn_dev.py moio_platform.asgi:application"""
import os

bind = [f"0.0.0.0:{os.getenv('BACKEND_PORT', '8093')}"]
worker_class = "uvloop"
workers = 1
accesslog = "-"
errorlog = "-"
loglevel = "debug"
graceful_timeout = 30

