# models.py
from django.db import models
from django.conf import settings
from central_hub.models import TenantScopedModel, Tenant  # Assuming your multi-tenant base

# Assuming a Tenant model exists in your project
# from your_tenant_app.models import Tenant


class EmailAccount(TenantScopedModel):
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    email_address = models.EmailField()
    imap_server = models.CharField(max_length=255)
    smtp_server = models.CharField(max_length=255)
    username = models.CharField(max_length=255)
    password = models.CharField(max_length=255)  # In production, use an encrypted field
    use_ssl = models.BooleanField(default=True)
    last_synced = models.DateTimeField(null=True, blank=True)
    ai_assistant_enabled = models.BooleanField(default=False)
    ai_assistant_id = models.CharField(max_length=255, null=True, blank=True)

    def __str__(self):
        return f"{self.email_address}"


class EmailMessage(TenantScopedModel):
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE)
    account = models.ForeignKey(EmailAccount, on_delete=models.CASCADE, related_name='emails')
    message_id = models.CharField(max_length=255, unique=True)
    subject = models.CharField(max_length=255)
    sender = models.EmailField()
    recipients = models.TextField()  # Can be a comma-separated string or JSON field
    body = models.TextField()
    date_received = models.DateTimeField()
    is_read = models.BooleanField(default=False)
    folder = models.CharField(max_length=100, default='Inbox')

    def __str__(self):
        return f"{self.subject} from {self.sender}"
