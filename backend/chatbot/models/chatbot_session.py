import uuid

from django.db import models

from central_hub.models import Tenant, TenantScopedModel


class ChatbotAssistant(TenantScopedModel):

    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    openai_assistant_id = models.CharField(max_length=200, blank=True, default="")
    name = models.CharField(max_length=100,  null=False)
    description = models.CharField(max_length=200, null=False)
    instructions = models.TextField(default="")
    model = models.CharField(max_length=50, null=False)
    file_search = models.BooleanField(default=False)
    code_interpreter = models.BooleanField(default=False)
    functions = models.TextField(default="")
    json_object = models.BooleanField(default=False)
    temperature = models.FloatField(default=0)
    top_p = models.FloatField(default=1)
    created = models.DateTimeField(auto_now_add=True)
    updated = models.DateTimeField(auto_now=True)
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE)
    default = models.BooleanField(default=False)

    def __str__(self):
        return f'{self.name}'

    class Meta:
        db_table = 'assistant'
        verbose_name_plural = "Assistants"

        constraints = [
                    models.UniqueConstraint(fields=['name', 'tenant'], name='unique_assistant_name_tenant')
                ]
