import json
import re

from fam.models import AssetRecord, FamLabel
from django.db import transaction


def get_asset_markers():
    assets = AssetRecord.objects.all()
    markers = []
    for asset in assets:
        m = {
            'lat': str(asset.last_known_latitude),
            'lng': str(asset.last_known_longitude),
            'title': asset.name
        }
        markers.append(m)
    if len(markers) == 0:
        print("No hay asset markers")

    return json.dumps(markers)


def create_labels(prefix, digits, quantity, tenant):
    created_labels = []
    for i in range(quantity):
        with transaction.atomic():
            # Find the highest existing company_tag with the same prefix
            regex_pattern = rf'^{prefix}\d+$'
            last_tag = FamLabel.objects.filter(company_tag__regex=regex_pattern, tenant=tenant).order_by('-company_tag').first()

            if last_tag:
                last_number = int(last_tag.company_tag[len(prefix):])
            else:
                last_number = 0

            next_number = last_number + 1
            company_tag = f'{prefix}{next_number:0{digits}d}'

            label = FamLabel(company_tag=company_tag, tenant=tenant)
            label.save()
            created_labels.append(label)
    return created_labels

