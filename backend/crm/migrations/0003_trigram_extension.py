# Generated manually for typo-tolerant search

from django.contrib.postgres.operations import TrigramExtension
from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("crm", "0002_initial"),
    ]

    operations = [
        TrigramExtension(),
    ]
