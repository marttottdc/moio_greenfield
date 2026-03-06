import uuid

from django.db import models
from django.utils import timezone

from crm.models import Contact
from portal.models import Tenant, TenantScopedModel
from django.db import models
from django.db.models.signals import post_save
from django.dispatch import receiver

from portal.models import Tenant
from moio_platform.core.events import emit_event


class ConversationRole(models.TextChoices):
    USER = 'USER', 'User'
    SYSTEM = 'SYSTEM', 'System'
    ASSISTANT = 'ASSISTANT', 'Assistant'


class ChatbotSession(TenantScopedModel):

    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, default=1)
    session = models.CharField(max_length=100, unique=True, default=uuid.uuid4, editable=False, primary_key=True)
    id = models.UUIDField(null=True)

    contact = models.ForeignKey(Contact, related_name="chatbot_session", on_delete=models.CASCADE)
    start = models.DateTimeField(null=True)
    end = models.DateTimeField(null=True)
    last_interaction = models.DateTimeField(null=True, auto_now=True)
    started_by = models.CharField(max_length=100, null=True, blank=True)
    context = models.JSONField(null=True, blank=True)
    final_summary = models.TextField(null=True, blank=True)
    channel = models.CharField(max_length=40, null=True)
    active = models.BooleanField(default=True)
    busy = models.BooleanField(default=False)
    multi_message = models.BooleanField(default=False)
    experience = models.CharField(max_length=40, null=True, blank=True)
    human_mode = models.BooleanField(default=False)
    thread_id = models.CharField(max_length=100, default="")
    assistant_id = models.CharField(max_length=100, default="")
    agent_id = models.UUIDField(null=True, blank=True)
    csat = models.IntegerField(null=True, blank=True)
    current_agent = models.CharField(max_length=100, default="")
    agent_input_thread = models.TextField(null=True)

    class Meta:
        db_table = 'chatbot_session'

    def __str__(self):
        return str(self.pk)

    def save(self, *args, **kwargs):
        # Ensure id matches session (convert session string to UUID)
        if self.session and self.id is None:
            self.id = self.session
        super().save(*args, **kwargs)

    def close(self):
        self.end = timezone.now()
        self.active = False
        self.save()

        try:
            emit_event(
                name="chatbot_session.inactivated",
                tenant_id=self.tenant.tenant_code,
                actor={"type": "system", "id": "chatbot_session.close"},
                entity={"type": "chatbot_session", "id": str(self.session)},
                payload={
                    "session_id": str(self.session),
                    "contact_id": str(self.contact_id) if self.contact_id else None,
                    "contact_name": self.contact.fullname if self.contact else None,
                    "channel": self.channel,
                    "ended_at": self.end.isoformat() if self.end else None,
                    "active": bool(self.active),
                },
                source="model",
            )
        except Exception:
            pass


class ChatbotMemory(models.Model):

    session = models.ForeignKey(ChatbotSession, related_name="memory_thread", on_delete=models.CASCADE)
    role = models.CharField(max_length=45, null=True)
    content = models.TextField(null=False, default="")
    created = models.DateTimeField(auto_now_add=True)
    intent = models.TextField(null=True)
    subject_of_interest = models.CharField(max_length=200, null=True)
    stitches = models.IntegerField(default=0)
    skipped = models.IntegerField(default=0)
    author = models.CharField(max_length=180, default="")

    class Meta:
        db_table = 'chatbot_memory'


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
