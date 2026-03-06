import os

import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "moio_platform.test_settings")

django.setup()
