import uuid
from django.db import models
from central_hub.models import Tenant, TenantScopedModel
from django.db.models import Q, UniqueConstraint
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _

# Reusable channel definitions
CHANNEL_WHATSAPP = 'whatsapp'
CHANNEL_EMAIL = 'email'
CHANNEL_WEBHOOK = 'webhook'
CHANNEL_DESKTOP = 'desktop'
CHANNEL_WEB = 'web'
# Extend this list as needed
CHANNEL_FLOWS = 'flows'
CHANNEL_CHOICES = [
    (CHANNEL_WHATSAPP, 'WhatsApp'),
    (CHANNEL_EMAIL, 'Email'),
    (CHANNEL_WEBHOOK, 'Webhook'),
    (CHANNEL_DESKTOP, 'Desktop'),
    (CHANNEL_WEB, 'Web'),
    (CHANNEL_FLOWS, 'Flows'),
]


class AgentConfiguration(TenantScopedModel):

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    enabled = models.BooleanField(default=True)
    name = models.CharField(max_length=255, blank=True, null=True)
    model = models.CharField(max_length=80, default="chat-gpt-4o")
    instructions = models.TextField(default="", blank=True, null=True)
    # Use the reusable choices
    channel = models.CharField(
        max_length=80,
        choices=CHANNEL_CHOICES,
        help_text="Select the integration channel for this agent",
        null=True,
    )
    channel_id = models.CharField(max_length=80, blank=True, null=True)
    tools = models.JSONField(default=list, blank=True, null=True)
    enable_websearch = models.BooleanField(default=False)
    handoffs = models.ManyToManyField(
        'self',
        symmetrical=False,
        blank=True,
        help_text="Agents this agent can hand off to")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    default = models.BooleanField(default=False)
    model_settings = models.JSONField(
        default=dict,
        blank=True,
        help_text=_("JSON representation of the ModelSettings dataclass."))
    handoff_description = models.TextField(
        blank=True,
        null=True,
        help_text=_("Description of handoff behavior and routing logic"))
    guardrails = models.JSONField(
        default=dict,
        blank=True,
        help_text=_("Guardrail configurations with input/output arrays"))
    output = models.JSONField(
        default=dict,
        blank=True,
        help_text=_("Output configuration including model and format"))
    run_behavior = models.JSONField(
        default=dict,
        blank=True,
        help_text=_("Runtime behavior configuration"))

    class Meta:
        db_table = 'agent_configuration'
        verbose_name = "Agent Configuration"
        verbose_name_plural = "Agent Configurations"
        indexes = [models.Index(fields=['id'])]
        constraints = [
            # 1) Only one default=True per tenant
            UniqueConstraint(fields=['tenant'],
                             condition=Q(default=True),
                             name='unique_default_agent_per_tenant'),
            # 2) Name must be unique within a tenant
            UniqueConstraint(fields=['tenant', 'name'],
                             name='unique_agent_name_per_tenant'),
        ]

    def save(self, *args, **kwargs):
        # If setting this one as default, clear any others for the same tenant
        if self.default:
            AgentConfiguration.objects.filter(
                tenant=self.tenant,
                default=True).exclude(pk=self.pk).update(default=False)

        # Validate that we don’t orphan the tenant without a default, if you want to enforce always one default:
        # elif not AgentConfiguration.objects.filter(tenant=self.tenant, default=True).exclude(pk=self.pk).exists():
        #     raise ValidationError("Each tenant must have exactly one default agent.")

        super().save(*args, **kwargs)

    def __str__(self):
        return self.name
