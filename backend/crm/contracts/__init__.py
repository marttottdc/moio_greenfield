"""CRM Contracts registry for Flow CRM CRUD node.

These contracts describe which resources exist (contact/ticket/deal/audience),
which operations they support, and the JSON Schemas for configuring those ops.
"""

from .registry import get_all_resources, get_resource

__all__ = ["get_all_resources", "get_resource"]

