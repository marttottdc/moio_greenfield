from django.db import models

from central_hub.models import Tenant


class OpenaiConfiguration(models.Model):

    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, default=1)
    name = models.CharField(max_length=100, default="openai configuration", editable=False)
    api_key = models.CharField(max_length=500)
    max_retries = models.IntegerField(default=5)
    created = models.DateTimeField(auto_now_add=True, editable=False)
    default_model = models.CharField(max_length=100, default="gpt-4")

    def save(self, *args, **kwargs):
        self.pk = 1  # set the primary key to 1
        super().save(*args, **kwargs)
