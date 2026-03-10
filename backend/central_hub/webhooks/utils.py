"""Re-export from tenancy. Use tenancy.webhooks.utils directly for new code."""
from tenancy.webhooks.utils import (
    available_handlers,
    get_handler,
    generate_auth_config,
    trigger_webhook_flows,
)

__all__ = ["available_handlers", "get_handler", "generate_auth_config", "trigger_webhook_flows"]
