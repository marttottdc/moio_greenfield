"""Re-export from tenancy for backward compatibility."""
from tenancy.entitlements_defaults import (
    BUSINESS,
    FREE,
    PRO,
    get_default_entitlements_for_plan,
    get_default_features_for_plan,
    get_default_limits_for_plan,
)

__all__ = [
    "BUSINESS",
    "FREE",
    "PRO",
    "get_default_entitlements_for_plan",
    "get_default_features_for_plan",
    "get_default_limits_for_plan",
]
