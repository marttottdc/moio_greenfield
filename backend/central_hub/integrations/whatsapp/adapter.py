"""
WhatsApp Integration Adapter (Integrations Hub contract).

Official platform wrapper for WhatsApp Business API.
Validates multi-instance (phone_number_id as instance_id) and webhook-heavy behavior.
Delegates webhook handling to existing chatbot receiver; connect via embedded signup.
"""

from __future__ import annotations

import logging
from typing import Any

from django.http import HttpRequest, HttpResponse

from central_hub.integrations.contract import (
    IntegrationAdapter,
    IntegrationBindingStatus,
)

logger = logging.getLogger(__name__)


class WhatsAppAdapter(IntegrationAdapter):
    slug = "whatsapp"

    def connect(self, tenant_id: int, instance_id: str, credentials: dict[str, Any]) -> dict[str, Any]:
        """Embedded signup is handled by WhatsappEmbeddedSignupCompleteView; adapter reports status."""
        from central_hub.integrations.models import IntegrationConfig

        config = IntegrationConfig.objects.filter(
            tenant_id=tenant_id,
            slug=self.slug,
            instance_id=instance_id,
        ).first()
        if config and config.enabled and config.config.get("token"):
            return {
                "instance_id": instance_id,
                "status": IntegrationBindingStatus.CONNECTED.value,
                "message": "Use embedded signup flow to connect.",
            }
        return {
            "instance_id": instance_id,
            "status": IntegrationBindingStatus.PENDING_LINK.value,
            "message": "Use embedded signup flow to connect.",
        }

    def disconnect(self, tenant_id: int, instance_id: str) -> None:
        """Disable and clear credentials for this WhatsApp instance."""
        from central_hub.integrations.models import IntegrationConfig, IntegrationBindingStatus

        config = IntegrationConfig.objects.filter(
            tenant_id=tenant_id,
            slug=self.slug,
            instance_id=instance_id,
        ).first()
        if config:
            config.enabled = False
            config.status = IntegrationBindingStatus.DISABLED
            config.config.pop("token", None)
            config.save(update_fields=["enabled", "status", "config", "updated_at"])

    def validate(self, tenant_id: int, instance_id: str, config: dict[str, Any] | None) -> tuple[bool, str]:
        """Validate WhatsApp token/phone_id (optional: call Graph API to verify)."""
        from central_hub.integrations.models import IntegrationConfig

        if config is None:
            cfg = IntegrationConfig.objects.filter(
                tenant_id=tenant_id,
                slug=self.slug,
                instance_id=instance_id,
            ).first()
            config = (cfg.config if cfg else {}) or {}

        token = (config.get("token") or "").strip()
        phone_id = (config.get("phone_id") or "").strip()
        if not token or not phone_id:
            return False, "Token and phone_id are required"
        # Optional: GET /phone_numbers to verify; for now just structure check
        return True, "Config valid"

    def handle_webhook(
        self,
        request: HttpRequest,
        topic: str,
        payload: dict[str, Any],
        headers: dict[str, str],
    ) -> HttpResponse:
        """Delegate to existing chatbot WhatsApp webhook receiver (verify + queue)."""
        from chatbot.views import whatsapp_webhook_receiver
        return whatsapp_webhook_receiver(request)

    def health(self, tenant_id: int, instance_id: str) -> dict[str, Any]:
        """Return status and last_connection from config metadata."""
        from central_hub.integrations.models import IntegrationConfig

        cfg = IntegrationConfig.objects.filter(
            tenant_id=tenant_id,
            slug=self.slug,
            instance_id=instance_id,
        ).first()
        if not cfg:
            return {"status": "not_found"}
        meta = cfg.metadata or {}
        return {
            "status": getattr(cfg, "status", IntegrationBindingStatus.CONNECTED.value),
            "last_connection_ok": meta.get("last_connection_ok"),
            "last_connection_at": meta.get("last_connection_at"),
        }

    def public_summary(self, tenant_id: int, instance_id: str) -> dict[str, Any]:
        """Safe summary for hub UI (no secrets)."""
        from central_hub.integrations.models import IntegrationConfig

        cfg = IntegrationConfig.objects.filter(
            tenant_id=tenant_id,
            slug=self.slug,
            instance_id=instance_id,
        ).first()
        if not cfg:
            return {
                "slug": self.slug,
                "instance_id": instance_id,
                "status": IntegrationBindingStatus.PENDING_LINK.value,
            }
        return {
            "slug": self.slug,
            "instance_id": instance_id,
            "name": cfg.name or instance_id,
            "status": getattr(cfg, "status", IntegrationBindingStatus.CONNECTED.value),
            "enabled": cfg.enabled,
        }
