"""Re-export from tenancy for backward compatibility."""
from tenancy.entitlements_defaults import get_default_entitlements_for_plan

__all__ = [
    "get_default_entitlements_for_plan",
]
