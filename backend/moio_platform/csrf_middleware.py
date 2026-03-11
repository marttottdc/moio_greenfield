"""
Dynamic CSRF trusted-origins middleware.

Django's stock CsrfViewMiddleware builds its set of trusted origins once at
__init__ time from settings.CSRF_TRUSTED_ORIGINS.  This subclass extends that
set at runtime with the public app URL stored in PlatformConfiguration.my_url
(the tunnel/production URL entered by the admin), so that changing the tunnel
URL in the admin panel takes effect without restarting the server.

Usage – replace in settings.MIDDLEWARE:
    'django.middleware.csrf.CsrfViewMiddleware'
  with:
    'moio_platform.csrf_middleware.DynamicCsrfMiddleware'
"""

from __future__ import annotations

import logging
import time
from urllib.parse import urlparse

from django.middleware.csrf import CsrfViewMiddleware

logger = logging.getLogger(__name__)

# How long (seconds) to cache the DB value per worker process.
# Keeping it short means URL changes are picked up quickly without a restart.
_CACHE_TTL = 30


def _origin_from_url(url: str) -> str:
    """Return 'scheme://host' from a full URL, or empty string on failure."""
    try:
        parsed = urlparse((url or "").rstrip("/"))
        if parsed.scheme in ("http", "https") and parsed.netloc:
            return f"{parsed.scheme}://{parsed.netloc}"
    except Exception:
        pass
    return ""


class DynamicCsrfMiddleware(CsrfViewMiddleware):
    """
    CsrfViewMiddleware that adds PlatformConfiguration.my_url to the trusted
    origins set on each request (cached for _CACHE_TTL seconds per worker).
    """

    # Class-level cache shared across all requests in this worker process.
    _cached_origin: str = ""
    _cache_ts: float = 0.0

    def process_view(self, request, callback, callback_args, callback_kwargs):
        self._sync_trusted_origin()
        return super().process_view(request, callback, callback_args, callback_kwargs)

    def _sync_trusted_origin(self) -> None:
        """Refresh the cached dynamic origin and ensure it is in the trusted set."""
        now = time.monotonic()
        if now - DynamicCsrfMiddleware._cache_ts < _CACHE_TTL:
            # Cache is still fresh – just make sure it is in the set
            if DynamicCsrfMiddleware._cached_origin:
                self.allowed_origins_exact.add(DynamicCsrfMiddleware._cached_origin)
            return

        # Cache expired – re-read from DB
        origin = ""
        try:
            from central_hub.models import PlatformConfiguration  # noqa: PLC0415
            config = PlatformConfiguration.objects.only("my_url").first()
            origin = _origin_from_url(config.my_url if config else "")
        except Exception:
            logger.debug("DynamicCsrfMiddleware: could not read PlatformConfiguration", exc_info=True)

        DynamicCsrfMiddleware._cached_origin = origin
        DynamicCsrfMiddleware._cache_ts = now

        if origin:
            self.allowed_origins_exact.add(origin)
            logger.debug("DynamicCsrfMiddleware: trusting origin %s", origin)
