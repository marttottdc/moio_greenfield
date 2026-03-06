"""
Global API exception handler: single place for all API error responses.

Policy: only managed messages to the frontend. No raw exception text, tracebacks, or
uncontrolled content. Log full details server-side; return fixed, safe messages to the client.

- Known DRF exceptions (ValidationError, PermissionDenied, NotFound, etc.): use default
  handler and add "ok": False to the response body when it's a dict.
- Any other (unhandled) exception: log with error_id, path, method, and full traceback.
  Return 500 JSON with a fixed user message and error_id only (no str(exc), no traceback).
"""
import logging
import uuid

from rest_framework.views import exception_handler
from rest_framework.response import Response

logger = logging.getLogger(__name__)

# Message shown to the user; no stack traces or internal details
FRONTEND_MESSAGE = (
    "Something went wrong. Please try again. "
    "If the problem persists, contact support and provide the error reference below."
)


def api_exception_handler(exc, context):
    """
    DRF custom exception handler.

    - Known DRF/API exceptions: use default handler (proper status + detail).
    - Any other exception: log with error_id, return 500 JSON with friendly message + error_id.
    """
    response = exception_handler(exc, context)

    if response is not None:
        # DRF handled it (ValidationError, PermissionDenied, NotFound, etc.)
        # Ensure JSON shape has ok when possible for consistency
        if hasattr(response, "data") and isinstance(response.data, dict):
            response.data.setdefault("ok", False)
        return response

    # Unhandled exception: log fully, respond with generic message
    error_id = str(uuid.uuid4())
    request = context.get("request")
    path = getattr(request, "path", None) or getattr(request, "META", {}).get("PATH_INFO", "")
    method = getattr(request, "method", None) or ""

    logger.error(
        "api_error error_id=%s path=%s method=%s exc=%s",
        error_id,
        path,
        method,
        exc,
        exc_info=True,
        extra={"error_id": error_id, "path": path, "method": method},
    )

    return Response(
        {
            "ok": False,
            "error": FRONTEND_MESSAGE,
            "error_id": error_id,
        },
        status=500,
    )
