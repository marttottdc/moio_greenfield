import uuid

from django.db import models
from django.utils import timezone

from crm.models import Contact
from central_hub.models import Tenant, TenantScopedModel

from moio_platform.core.events import emit_event


class ConversationRole(models.TextChoices):
    USER = 'USER', 'User'
    SYSTEM = 'SYSTEM', 'System'
    ASSISTANT = 'ASSISTANT', 'Assistant'


class AgentSession(TenantScopedModel):
    """
    Agent session for a contact. PK is id (UUID).
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, default=1)
    contact = models.ForeignKey(Contact, related_name="agent_sessions", on_delete=models.CASCADE)
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
        db_table = 'agent_session'

    def __str__(self):
        return str(self.pk)

    def close(self):
        self.end = timezone.now()
        self.active = False
        self.save()

        try:
            event_id = emit_event(
                name="agent_session.inactivated",
                tenant_id=self.tenant.tenant_code,
                actor={"type": "system", "id": "agent_session.close"},
                entity={"type": "agent_session", "id": str(self.pk)},
                payload={
                    "session_id": str(self.pk),
                    "contact_id": str(self.contact_id) if self.contact_id else None,
                    "contact_name": self.contact.fullname if self.contact else None,
                    "channel": self.channel,
                    "ended_at": self.end.isoformat() if self.end else None,
                    "active": bool(self.active),
                },
                source="model",
            )
            try:
                from crm.services.event_activity_ingestion import create_activities_from_event
                create_activities_from_event(event_id)
            except Exception:
                pass
        except Exception:
            pass


class SessionThread(models.Model):
    """Thread of messages (memories) for an agent session. PK is UUID."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    session = models.ForeignKey(
        AgentSession, related_name="threads", on_delete=models.CASCADE
    )
    role = models.CharField(max_length=45, null=True)
    content = models.TextField(null=False, default="")
    created = models.DateTimeField(auto_now_add=True)
    intent = models.TextField(null=True)
    subject_of_interest = models.CharField(max_length=200, null=True)
    stitches = models.IntegerField(default=0)
    skipped = models.IntegerField(default=0)
    author = models.CharField(max_length=180, default="")

    class Meta:
        db_table = 'session_thread'
