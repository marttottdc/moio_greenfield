"""Re-export from tenancy. Use tenancy.webhooks.registry directly for new code."""
from tenancy.webhooks.registry import (
    webhook_handler,
    get_handler,
    get_available_handlers,
)

__all__ = ["webhook_handler", "get_handler", "get_available_handlers"]
