from contextvars import ContextVar
from typing import Any


current_tenant: ContextVar = ContextVar("current_tenant", default=None)


def set_current_tenant(tenant: Any):
    return current_tenant.set(tenant)
