from django.db import models
from django.utils import timezone

from central_hub.models import Tenant


class WaMessageLog(models.Model):

    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, default=1)
    entry_id = models.CharField(max_length=100, null=True)
    display_phone_number = models.CharField(max_length=100, null=True)
    phone_number_id = models.CharField(max_length=100, null=True)
    type = models.CharField(max_length=100, null=True)
    created = models.DateTimeField(auto_now_add=True, null=False, db_index=True)
    user_number = models.CharField(max_length=100, null=True)
    user_name = models.CharField(max_length=100, null=True)
    user_message = models.TextField(null=True)
    body = models.TextField(null=True)
    msg_content = models.JSONField(null=True)
    msg_id = models.CharField(max_length=200, null=True)
    context_msg_id = models.CharField(max_length=200, null=True)
    status = models.CharField(max_length=100, null=True, db_index=True)
    updated = models.DateTimeField(auto_now=True, null=False)
    recipient_id = models.CharField(max_length=100, null=True)
    conversation_id = models.CharField(max_length=200, null=True)
    expiration = models.DateTimeField(null=True)
    origin = models.CharField(max_length=100, null=True)
    timestamp = models.DateTimeField(null=True)
    
    flow_execution_id = models.UUIDField(
        null=True,
        blank=True,
        db_index=True,
        help_text="Links to FlowExecution for tracing messages sent via flows"
    )
    api_response = models.JSONField(
        null=True,
        blank=True,
        help_text="Full WhatsApp API response from send operation"
    )

    class Meta:
        db_table = 'wa_message_log'
        indexes = [
            models.Index(fields=["tenant", "created"], name="wa_log_tenant_created_idx"),
            models.Index(fields=["tenant", "status"], name="wa_log_tenant_status_idx"),
            models.Index(fields=["flow_execution_id"], name="wa_log_flow_exec_idx"),
        ]

