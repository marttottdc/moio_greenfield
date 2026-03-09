from django.core.management.base import BaseCommand
from fam.core.layouts import LAYOUTS as CODE_LAYOUTS
from fam.models import LabelLayout


count = 0
for key, elements in CODE_LAYOUTS.items():
    obj, created = LabelLayout.objects.update_or_create(
        key=key,
        defaults={"elements": elements, "description": "Imported from code"},
    )
    count += 1
