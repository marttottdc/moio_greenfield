"""
Re-export agent console runtime service from agent_console (deprecated).
Use agent_console.services.runtime_service instead.
"""
from __future__ import annotations

from agent_console.services.runtime_service import (
    OpenAINotConfiguredError,
    get_runtime_backend_for_user,
    runtime_initiator_from_user,
    runtime_scope_from_user,
)

__all__ = [
    "OpenAINotConfiguredError",
    "get_runtime_backend_for_user",
    "runtime_initiator_from_user",
    "runtime_scope_from_user",
]
