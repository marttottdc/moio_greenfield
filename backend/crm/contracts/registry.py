from __future__ import annotations

from typing import List

from .base import ResourceContract
from .activity import activity_contract, activity_suggestion_contract
from .contact import contact_contract
from .ticket import ticket_contract
from .deal import deal_contract
from .audience import audience_contract


_RESOURCE_BUILDERS = {
    "activity": activity_contract,
    "activity_suggestion": activity_suggestion_contract,
    "contact": contact_contract,
    "ticket": ticket_contract,
    "deal": deal_contract,
    "audience": audience_contract,
}


def get_all_resources() -> List[ResourceContract]:
    """Return all CRM resource contracts supported by the platform."""
    return [builder() for _, builder in sorted(_RESOURCE_BUILDERS.items())]


def get_resource(slug: str) -> ResourceContract | None:
    """Return a single resource contract, or None if unknown."""
    builder = _RESOURCE_BUILDERS.get(str(slug or "").strip().lower())
    return builder() if builder else None


__all__ = ["get_all_resources", "get_resource"]

