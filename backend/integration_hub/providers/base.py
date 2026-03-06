"""
Base provider interface for the Integration Hub.

All API providers (Moio, HubSpot, etc.) implement this interface.
Credentials are resolved at call time; never stored in the agent view.
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, Optional


@dataclass
class RequestContext:
    """Context passed to every provider request (tenant, user, auth, audit)."""
    tenant_id: str
    user_id: str
    access_token: Optional[str] = None
    request_id: Optional[str] = None
    correlation_id: Optional[str] = None


@dataclass
class ProviderResult:
    """Structured result of a single API call."""
    ok: bool
    provider: str
    method: str
    path: str
    status_code: Optional[int] = None
    data: Optional[Dict[str, Any] | list | str] = None
    error: Optional[str] = None
    message: Optional[str] = None
    meta: Dict[str, Any] = field(default_factory=dict)


class APIProvider(ABC):
    """Pluggable API provider. Auth is resolved per-request from context/config."""

    @property
    @abstractmethod
    def name(self) -> str:
        pass

    @abstractmethod
    async def request(
        self,
        method: str,
        path: str,
        query: Optional[Dict[str, Any]] = None,
        body: Optional[Dict[str, Any] | list] = None,
        context: Optional[RequestContext] = None,
    ) -> ProviderResult:
        """Execute one HTTP request. Never raise; return ProviderResult."""
        pass
