import uuid
from django.db import models
from portal.models import Tenant, TenantScopedModel


class TenantToolConfiguration(TenantScopedModel):
    """
    Per-tenant customization of available tools for agents.
    All tools are synced on app startup with enabled=True by default.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE)
    tool_name = models.CharField(max_length=100)
    tool_type = models.CharField(
        max_length=20,
        choices=[('custom', 'Custom'), ('builtin', 'Built-in')],
    )
    enabled = models.BooleanField(default=True)
    custom_description = models.TextField(blank=True)
    custom_display_name = models.CharField(max_length=255, blank=True)
    default_params = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'tenant_tool_configuration'
        verbose_name = 'Tenant Tool Configuration'
        verbose_name_plural = 'Tenant Tool Configurations'
        unique_together = ('tenant', 'tool_name')
        indexes = [models.Index(fields=['tenant', 'tool_name'])]

    def __str__(self):
        return f"{self.tool_name}"
