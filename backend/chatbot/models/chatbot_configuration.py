from django.db import models
from central_hub.models import Tenant


class ChatbotConfiguration (models.Model):

    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, default=1)
    enabled = models.BooleanField(default=True)
    summarizer_prompt = models.TextField(default="")
    chatbot_prompt = models.TextField(default="")
    experience = models.CharField(max_length=80, default="", unique=True, null=False)
    model = models.CharField(max_length=80, default="chat-gpt-4o")
    personality = models.TextField(default="")
    instructions = models.TextField(default="")
    sweeper_instructions = models.TextField(default="")
    channel = models.CharField(max_length=80, default="")
    channel_id = models.CharField(max_length=80, default="")

    class Meta:
        db_table = 'chatbot_configuration'

    def __str__(self):
        # Retorna una representación en cadena del objeto, por ejemplo, el valor del campo 'nombre'
        return self.experience
