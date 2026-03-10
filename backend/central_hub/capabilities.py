"""Re-export from tenancy. Use tenancy.capabilities directly for new code."""
from tenancy.capabilities import (
    CAPABILITY_KEYS,
    ROLE_CAPABILITIES,
    EffectiveCapabilities,
    get_effective_capabilities,
)

__all__ = [
    "CAPABILITY_KEYS",
    "ROLE_CAPABILITIES",
    "EffectiveCapabilities",
    "get_effective_capabilities",
]
