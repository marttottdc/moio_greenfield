from __future__ import annotations

from typing import Dict, Any

import requests
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from google.oauth2 import id_token as google_id_token
from google.auth.transport import requests as google_requests
import msal

from portal.models import PortalConfiguration


GOOGLE_SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/calendar.readonly",
    "openid",
    "email",
    "profile",
]

MICROSOFT_SCOPES = [
    "https://graph.microsoft.com/Mail.Read",
    "https://graph.microsoft.com/Calendars.Read",
    "offline_access",
    "openid",
    "email",
    "profile",
]


def _config_value(field: str, setting_name: str) -> str:
    cfg = PortalConfiguration.objects.first()
    val = getattr(cfg, field, "") if cfg else ""
    if val:
        return val
    value = getattr(settings, setting_name, None)
    if not value:
        raise ImproperlyConfigured(f"Missing setting {setting_name} and PortalConfiguration.{field}")
    return value


def google_authorize_url(redirect_uri: str, state: str) -> str:
    client_id = _config_value("google_oauth_client_id", "GOOGLE_OAUTH_CLIENT_ID")
    scope = " ".join(GOOGLE_SCOPES)
    return (
        "https://accounts.google.com/o/oauth2/v2/auth?"
        f"response_type=code&client_id={client_id}"
        f"&redirect_uri={redirect_uri}"
        f"&scope={scope}"
        f"&access_type=offline&prompt=consent&state={state}"
    )


def google_exchange_code(code: str, redirect_uri: str) -> Dict[str, Any]:
    client_id = _config_value("google_oauth_client_id", "GOOGLE_OAUTH_CLIENT_ID")
    client_secret = _config_value("google_oauth_client_secret", "GOOGLE_OAUTH_CLIENT_SECRET")
    token_url = "https://oauth2.googleapis.com/token"
    resp = requests.post(
        token_url,
        data={
            "code": code,
            "client_id": client_id,
            "client_secret": client_secret,
            "redirect_uri": redirect_uri,
            "grant_type": "authorization_code",
        },
        timeout=20,
    )
    resp.raise_for_status()
    return resp.json()


def google_refresh(credentials: Dict[str, Any]) -> Dict[str, Any]:
    refresh_token = credentials.get("refresh_token")
    if not refresh_token:
        raise ValueError("Missing refresh_token for Google credentials")
    client_id = _config_value("google_oauth_client_id", "GOOGLE_OAUTH_CLIENT_ID")
    client_secret = _config_value("google_oauth_client_secret", "GOOGLE_OAUTH_CLIENT_SECRET")
    resp = requests.post(
        "https://oauth2.googleapis.com/token",
        data={
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
            "client_id": client_id,
            "client_secret": client_secret,
        },
        timeout=20,
    )
    resp.raise_for_status()
    data = resp.json()
    data.setdefault("refresh_token", refresh_token)
    return data


def google_email_from_id_token(id_tok: str) -> str | None:
    try:
        payload = google_id_token.verify_oauth2_token(id_tok, google_requests.Request())
        return payload.get("email")
    except Exception:
        return None


def microsoft_app() -> msal.ConfidentialClientApplication:
    client_id = _config_value("microsoft_oauth_client_id", "MICROSOFT_OAUTH_CLIENT_ID")
    client_secret = _config_value("microsoft_oauth_client_secret", "MICROSOFT_OAUTH_CLIENT_SECRET")
    authority = getattr(settings, "MICROSOFT_OAUTH_AUTHORITY", "https://login.microsoftonline.com/common")
    return msal.ConfidentialClientApplication(
        client_id=client_id,
        client_credential=client_secret,
        authority=authority,
    )


def microsoft_authorize_url(redirect_uri: str, state: str) -> str:
    app = microsoft_app()
    return app.get_authorization_request_url(scopes=MICROSOFT_SCOPES, redirect_uri=redirect_uri, state=state)


def microsoft_exchange_code(code: str, redirect_uri: str) -> Dict[str, Any]:
    app = microsoft_app()
    result = app.acquire_token_by_authorization_code(code, scopes=MICROSOFT_SCOPES, redirect_uri=redirect_uri)
    if "access_token" not in result:
        raise ValueError(result.get("error_description") or "Microsoft token exchange failed")
    return result


def microsoft_refresh(credentials: Dict[str, Any]) -> Dict[str, Any]:
    refresh_token = credentials.get("refresh_token")
    if not refresh_token:
        raise ValueError("Missing refresh_token for Microsoft credentials")
    app = microsoft_app()
    result = app.acquire_token_by_refresh_token(refresh_token, scopes=MICROSOFT_SCOPES)
    if "access_token" not in result:
        raise ValueError(result.get("error_description") or "Microsoft token refresh failed")
    result.setdefault("refresh_token", refresh_token)
    return result


def microsoft_get_profile(access_token: str) -> Dict[str, Any]:
    resp = requests.get(
        "https://graph.microsoft.com/v1.0/me",
        headers={"Authorization": f"Bearer {access_token}"},
        timeout=20,
    )
    resp.raise_for_status()
    return resp.json()

