"""Re-export from tenancy for backward compatibility."""
from tenancy.context_utils import current_tenant, set_current_tenant

__all__ = ["current_tenant", "set_current_tenant"]
