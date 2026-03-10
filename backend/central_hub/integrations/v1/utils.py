from __future__ import annotations

from django.conf import settings
from django.urls import reverse
from central_hub.models import PlatformConfiguration


def api_error(code: str, message: str):
    return {"error": {"code": code, "message": message}}


def public_base_url() -> str:
    cfg = PlatformConfiguration.objects.first()
    base = (cfg.my_url if cfg else getattr(settings, "PUBLIC_BASE_URL", "") or "").rstrip("/")
    return base or "http://localhost:8000"


def build_callback_url(provider: str) -> str:
    base = public_base_url()
    path = reverse("integrations_email_oauth_callback", kwargs={"provider": provider})
    return f"{base}{path}"

