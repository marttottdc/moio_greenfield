import uuid
import jwt
from datetime import datetime, timezone
from django.db import models
from django.conf import settings
import time


class ServiceToken(models.Model):
    """
    Service-to-service authentication tokens with scope-based access control.
    Used for protecting API endpoints with granular permission scopes.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    service_name = models.CharField(
        max_length=100,
        help_text=
        "Service identifier (e.g., fluidland, cms_renderer, webhook_processor)"
    )
    scopes = models.JSONField(
        default=list,
        blank=True,
        help_text=
        "List of allowed scopes (e.g., pages.read, tenant.config.read)")
    tenant_id = models.CharField(
        max_length=50,
        blank=True,
        null=True,
        help_text=
        "Optional tenant restriction. Leave blank for multi-tenant access.")
    duration_hours = models.PositiveIntegerField(
        default=24,
        help_text="Token validity period in hours",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField(blank=True, null=True)
    token = models.TextField(blank=True,
                             help_text="Auto-generated signed JWT token")
    is_active = models.BooleanField(default=True)

    class Meta:
        verbose_name = "Service Token"
        verbose_name_plural = "Service Tokens"
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.service_name} ({'active' if self.is_active else 'inactive'})"

    def generate_token(self):
        """Generate a new JWT token for this service."""
        now = int(time.time())
        exp_ts = now + (self.duration_hours * 3600)

        payload = {
            "iss": self.service_name,
            "sub": f"service:{self.service_name}",
            "aud": "moio_platform",
            "scopes": self.scopes or [],
            "iat": now,
            "nbf": now - 1,  # tolerancia
            "exp": exp_ts,
        }

        if self.tenant_id:
            payload["tenant_id"] = self.tenant_id

        secret = settings.SERVICE_TOKEN_SECRET
        self.token = jwt.encode(payload, secret, algorithm="HS256")

        self.expires_at = datetime.fromtimestamp(exp_ts, tz=timezone.utc)

        self.save()

        return self.token
