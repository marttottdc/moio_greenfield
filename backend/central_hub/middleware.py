"""Re-export from tenancy. Use tenancy.middleware directly for new code."""
from tenancy.middleware import TenantMiddleware

__all__ = ["TenantMiddleware"]
