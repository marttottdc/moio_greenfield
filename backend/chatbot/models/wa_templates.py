from django.db import models

from portal.models import Tenant


class WaTemplate(models.Model):

    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, default=1)
    status = models.CharField(max_length=80, null=True)
    template_id = models.CharField(max_length=80, null=False, unique=True)
    language = models.CharField(max_length=10)
    category = models.CharField(max_length=80, null=True)
    name = models.CharField(max_length=200, null=False)
    components = models.JSONField()
    whatsapp_business_account_id = models.CharField(max_length=100, null=True)

    class Meta:
        db_table = 'wa_template'

    def __str__(self):
        return self.name


class WaTemplateComponent(models.Model):
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, default=1)
    template = models.ForeignKey(WaTemplate, on_delete=models.CASCADE)
    format = models.CharField(max_length=40, null=True)
    example = models.TextField(default="")
    text = models.TextField(default="")
    buttons = models.TextField(default="")
    component_type = models.CharField(max_length=40, null=True)

    def __str__(self):
        return f"{self.template.name} - {self.component_type}"

