"""Per-tenant chatbot/assistant/agent configuration. Lives in chatbot app."""
from django.db import models

from central_hub.models import Tenant


class TenantChatbotSettings(models.Model):
    """
    Chatbot, assistant, and agent configuration per tenant.

    Replaces corresponding fields formerly on Tenant. One row per tenant.
    """
    tenant = models.OneToOneField(Tenant, on_delete=models.CASCADE, related_name="chatbot_settings")
    assistants_enabled = models.BooleanField(default=False)
    assistants_default_id = models.CharField(max_length=200, null=True, blank=True, default="")
    conversation_handler = models.CharField(
        max_length=40,
        choices=[("chatbot", "Chatbot"), ("assistant", "Assistant"), ("agent", "Agent")],
        default="assistant",
    )
    assistant_smart_reply_enabled = models.BooleanField(default=False)
    assistant_output_formatting_instructions = models.TextField(null=True, blank=True, default="")
    assistant_output_schema = models.TextField(null=True, blank=True, default="")
    assistants_inactivity_limit = models.IntegerField(default=30)
    chatbot_enabled = models.BooleanField(default=False)
    default_agent_id = models.URLField(null=True, blank=True, default="")
    agent_allow_reopen_session = models.BooleanField(default=False)
    agent_reopen_threshold = models.IntegerField(default=360)

    class Meta:
        db_table = "chatbot_tenant_chatbot_settings"
        verbose_name = "Tenant Chatbot Settings"
        verbose_name_plural = "Tenant Chatbot Settings"

    def __str__(self):
        return f"Chatbot settings for {self.tenant.nombre}"
