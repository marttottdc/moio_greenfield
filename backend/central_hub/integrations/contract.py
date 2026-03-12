"""
Integrations Hub Contract

Canonical definition of:
- Binding status (single normalized status model for UI, admin, workers)
- IntegrationAdapter interface (official platform wrapper per provider)
- Router contract for inbound webhooks/OAuth/task dispatch

All integrations conform to this contract; IntegrationConfig is the
storage/compatibility layer for binding state and config.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from django.http import HttpRequest, HttpResponse


class IntegrationBindingStatus(str, Enum):
    """
    Single normalized status for an integration binding.
    Used by tenant hub, platform admin, and workers.
    """
    CONNECTED = "connected"
    INVALID_CREDENTIALS = "invalid_credentials"
    UNINSTALLED = "uninstalled"
    PENDING_LINK = "pending_link"
    DISABLED = "disabled"
    SYNCING = "syncing"


@dataclass
class BindingResolution:
    """Result of resolving an inbound request (webhook/OAuth) to a tenant binding."""
    tenant_id: int
    slug: str
    instance_id: str
    config_id: str | None  # IntegrationConfig pk if applicable
    status: IntegrationBindingStatus
    adapter: "IntegrationAdapter | None" = None
    raw_config: dict[str, Any] | None = None


class IntegrationAdapter(ABC):
    """
    Official platform wrapper for a provider.

    Encapsulates provider API client and auth handling.
    Owns inbound payload normalization and outbound calls.
    No raw provider calls outside the adapter boundary.
    """

    slug: str = ""

    @abstractmethod
    def connect(self, tenant_id: int, instance_id: str, credentials: dict[str, Any]) -> dict[str, Any]:
        """
        Establish or refresh connection (e.g. OAuth exchange, token store).
        Returns normalized result (e.g. { "instance_id": "...", "status": "connected" }).
        """
        ...

    @abstractmethod
    def disconnect(self, tenant_id: int, instance_id: str) -> None:
        """Revoke or remove connection; clear secrets for this binding."""
        ...

    @abstractmethod
    def validate(self, tenant_id: int, instance_id: str, config: dict[str, Any] | None) -> tuple[bool, str]:
        """
        Validate credentials/config. Returns (success, message).
        Uses stored config if config is None.
        """
        ...

    def sync(
        self,
        tenant_id: int,
        instance_id: str,
        options: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """
        Run sync (pull/push) for this binding. Optional options dict for scope.
        Returns result summary, e.g. { "status": "ok", "counts": {...} }.
        """
        return {"status": "skipped", "reason": "not_implemented"}

    def handle_webhook(
        self,
        request: "HttpRequest",
        topic: str,
        payload: dict[str, Any],
        headers: dict[str, str],
    ) -> "HttpResponse":
        """
        Verify, normalize, and dispatch webhook. Returns HTTP response.
        Adapter is responsible for verification (HMAC etc.) and routing to tenant.
        """
        raise NotImplementedError(f"Webhook not implemented for {self.slug}")

    def health(self, tenant_id: int, instance_id: str) -> dict[str, Any]:
        """
        Return health/status for this binding (e.g. last_ok, last_error).
        """
        return {"status": "unknown"}

    def public_summary(self, tenant_id: int, instance_id: str) -> dict[str, Any]:
        """
        Safe summary for tenant UI (no secrets): name, status, instance label.
        """
        return {
            "slug": self.slug,
            "instance_id": instance_id,
            "status": IntegrationBindingStatus.CONNECTED.value,
        }


class WebhookRouterContract:
    """
    Contract for routing inbound webhooks to the correct integration and tenant.

    Each integration has its own path, e.g. /api/v1/integrations/shopify/webhook/.
    The router resolves: definition -> binding -> adapter -> dispatch.
    """

    @staticmethod
    def resolve(slug: str, request: "HttpRequest") -> BindingResolution | None:
        """
        Resolve slug + request to a BindingResolution.
        Returns None if slug is unknown or resolution fails.
        """
        from central_hub.integrations.registry import get_integration

        definition = get_integration(slug)
        if not definition or not getattr(definition, "adapter_module", None):
            return None
        # Adapter performs verification and resolution (e.g. from X-Shopify-Shop-Domain).
        adapter = get_adapter(slug)
        if not adapter:
            return None
        # Resolution is adapter-specific (e.g. Shopify uses shop_domain from headers).
        return None  # Overridden per integration in Phase 2


def get_adapter(slug: str) -> IntegrationAdapter | None:
    """Return the adapter instance for the given integration slug, or None."""
    from central_hub.integrations.registry import get_integration

    definition = get_integration(slug)
    if not definition:
        return None
    adapter_module = getattr(definition, "adapter_module", None)
    if not adapter_module:
        return None
    try:
        from django.utils.module_loading import import_string
        adapter_class = import_string(adapter_module)
        return adapter_class()
    except Exception:
        return None
