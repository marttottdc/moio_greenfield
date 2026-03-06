import json
import os
from celery import shared_task, current_task
from django.utils import timezone
from fam.models import AssetScanDetails
from fam.models import AssetRecord
from django.conf import settings


@shared_task(queue=settings.MEDIUM_PRIORITY_Q)
def process_received_scan(body):

    task_id = current_task.request.id
    print(f"Processing task ---> {task_id}")
    full_body = json.dumps(body)
    print(body)
    try:
        # comienzo del programa principal

        payload = AssetScanDetails(
            address=body['address'],
            last_seen=body['last_seen'],
            name=body['name'],
            rssi=body['rssi'],
            scanned_by=body['custom_name'],
            latitude=body['latitude'],
            longitude=body['longitude'],
            url=body['url'],
            received_date=timezone.now(),
            full_body=full_body
        )
        payload.save()

    except Exception as e:
        print(f'Error al insertar registro{e}')
        payload = AssetScanDetails(
            full_body=full_body
        )

    try:
        asset_record = AssetRecord.objects.get(mac_address=body['address'])
        asset_record.last_seen = body['last_seen']
        asset_record.last_known_latitude = body['latitude']
        asset_record.last_known_longitude = body['longitude']
        asset_record.last_update = timezone.now()
        asset_record.save()

    except Exception as e:
        print('Activo no encontrado, buscando por asset_id')
        asset_id = str(body['url'])
        asset_id = asset_id.split('/')[-1]
        asset_record = AssetRecord.objects.get(asset_id=asset_id)
        asset_record.last_seen = body['last_seen']
        asset_record.last_known_latitude = body['latitude']
        asset_record.last_known_longitude = body['longitude']
        asset_record.last_update = timezone.now()
        asset_record.save()

    except Exception as e:
        print('Activo no encontrado')





