from django.db import models

from portal.models import Tenant


class WaPayloads(models.Model):
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, default=1)
    wa_body = models.TextField(null=True)
    timestamp = models.TextField(null=True)
    status = models.TextField(null=True)

    class Meta:
        db_table = 'wa_payloads'
