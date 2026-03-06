from __future__ import annotations

from typing import Dict, Any, List, Tuple

import requests

from portal.integrations.v1.models import CalendarAccount

CAL_API_BASE = "https://www.googleapis.com/calendar/v3"
GRAPH_BASE = "https://graph.microsoft.com/v1.0"


class CalendarServiceError(Exception):
    pass


# ------------------------
# Google Calendar
# ------------------------


def google_list(credentials: dict, calendar_id: str, start: str | None, end: str | None, cursor: str | None, page_size: int) -> Tuple[List[Dict[str, Any]], str | None]:
    headers = {"Authorization": f"Bearer {credentials['access_token']}"}
    params: dict[str, Any] = {"maxResults": page_size, "singleEvents": "true", "orderBy": "startTime"}
    if start:
        params["timeMin"] = start
    if end:
        params["timeMax"] = end
    if cursor:
        params["pageToken"] = cursor
    resp = requests.get(f"{CAL_API_BASE}/calendars/{calendar_id}/events", headers=headers, params=params, timeout=20)
    resp.raise_for_status()
    data = resp.json()
    items = [_google_to_event(ev) for ev in data.get("items", [])]
    return items, data.get("nextPageToken")


def google_get(credentials: dict, calendar_id: str, event_id: str) -> Dict[str, Any]:
    headers = {"Authorization": f"Bearer {credentials['access_token']}"}
    resp = requests.get(f"{CAL_API_BASE}/calendars/{calendar_id}/events/{event_id}", headers=headers, timeout=20)
    resp.raise_for_status()
    return _google_to_event(resp.json())


def google_create(credentials: dict, calendar_id: str, payload: dict) -> str:
    headers = {"Authorization": f"Bearer {credentials['access_token']}", "Content-Type": "application/json"}
    body = _event_payload(payload)
    resp = requests.post(f"{CAL_API_BASE}/calendars/{calendar_id}/events", headers=headers, json=body, timeout=20)
    resp.raise_for_status()
    return resp.json().get("id")


def google_update(credentials: dict, calendar_id: str, event_id: str, payload: dict) -> Dict[str, Any]:
    headers = {"Authorization": f"Bearer {credentials['access_token']}", "Content-Type": "application/json"}
    body = _event_payload(payload)
    resp = requests.patch(f"{CAL_API_BASE}/calendars/{calendar_id}/events/{event_id}", headers=headers, json=body, timeout=20)
    resp.raise_for_status()
    return _google_to_event(resp.json())


def google_delete(credentials: dict, calendar_id: str, event_id: str) -> None:
    headers = {"Authorization": f"Bearer {credentials['access_token']}"}
    resp = requests.delete(f"{CAL_API_BASE}/calendars/{calendar_id}/events/{event_id}", headers=headers, timeout=20)
    resp.raise_for_status()


def _google_to_event(ev: dict) -> Dict[str, Any]:
    start = ev.get("start", {}) or {}
    end = ev.get("end", {}) or {}
    return {
        "id": ev.get("id"),
        "title": ev.get("summary"),
        "start": start.get("dateTime") or start.get("date"),
        "end": end.get("dateTime") or end.get("date"),
        "attendees": [a.get("email") for a in ev.get("attendees", []) if a.get("email")],
    }


def _event_payload(payload: dict) -> dict:
    return {
        "summary": payload.get("title"),
        "start": {"dateTime": payload.get("start")},
        "end": {"dateTime": payload.get("end")},
        "attendees": [{"email": a} for a in payload.get("attendees", [])],
    }


# ------------------------
# Outlook Calendar (Graph)
# ------------------------


def outlook_list(credentials: dict, start: str | None, end: str | None, cursor: str | None, page_size: int) -> Tuple[List[Dict[str, Any]], str | None]:
    headers = {"Authorization": f"Bearer {credentials['access_token']}"}
    params: dict[str, Any] = {"$top": page_size, "$orderby": "start/dateTime"}
    if start and end:
        # calendarView provides better range filtering
        url = f"{GRAPH_BASE}/me/calendarView"
        params["startDateTime"] = start
        params["endDateTime"] = end
    else:
        url = f"{GRAPH_BASE}/me/events"
    if cursor:
        params["$skiptoken"] = cursor
    resp = requests.get(url, headers=headers, params=params, timeout=20)
    resp.raise_for_status()
    data = resp.json()
    items = [_outlook_to_event(ev) for ev in data.get("value", [])]
    next_link = data.get("@odata.nextLink")
    next_cursor = None
    if next_link and "$skiptoken=" in next_link:
        next_cursor = next_link.split("$skiptoken=")[-1]
    return items, next_cursor


def outlook_get(credentials: dict, event_id: str) -> Dict[str, Any]:
    headers = {"Authorization": f"Bearer {credentials['access_token']}"}
    resp = requests.get(f"{GRAPH_BASE}/me/events/{event_id}", headers=headers, timeout=20)
    resp.raise_for_status()
    return _outlook_to_event(resp.json())


def outlook_create(credentials: dict, payload: dict) -> str:
    headers = {"Authorization": f"Bearer {credentials['access_token']}", "Content-Type": "application/json"}
    body = _outlook_event_payload(payload)
    resp = requests.post(f"{GRAPH_BASE}/me/events", headers=headers, json=body, timeout=20)
    resp.raise_for_status()
    return resp.json().get("id")


def outlook_update(credentials: dict, event_id: str, payload: dict) -> Dict[str, Any]:
    headers = {"Authorization": f"Bearer {credentials['access_token']}", "Content-Type": "application/json"}
    body = _outlook_event_payload(payload)
    resp = requests.patch(f"{GRAPH_BASE}/me/events/{event_id}", headers=headers, json=body, timeout=20)
    resp.raise_for_status()
    return _outlook_to_event(resp.json())


def outlook_delete(credentials: dict, event_id: str) -> None:
    headers = {"Authorization": f"Bearer {credentials['access_token']}"}
    resp = requests.delete(f"{GRAPH_BASE}/me/events/{event_id}", headers=headers, timeout=20)
    resp.raise_for_status()


def _outlook_to_event(ev: dict) -> Dict[str, Any]:
    start = ev.get("start", {}) or {}
    end = ev.get("end", {}) or {}
    return {
        "id": ev.get("id"),
        "title": ev.get("subject"),
        "start": start.get("dateTime"),
        "end": end.get("dateTime"),
        "attendees": [
            (a.get("emailAddress") or {}).get("address")
            for a in ev.get("attendees", [])
            if a.get("emailAddress")
        ],
    }


def _outlook_event_payload(payload: dict) -> dict:
    return {
        "subject": payload.get("title"),
        "start": {"dateTime": payload.get("start"), "timeZone": "UTC"},
        "end": {"dateTime": payload.get("end"), "timeZone": "UTC"},
        "attendees": [{"emailAddress": {"address": a}} for a in payload.get("attendees", [])],
    }


# ------------------------
# Dispatcher
# ------------------------


def list_events(account: CalendarAccount, start: str | None, end: str | None, cursor: str | None, page_size: int) -> tuple[list[dict], str | None]:
    creds = account.external_account.credentials
    provider = account.external_account.provider
    if provider == "google":
        return google_list(creds, account.calendar_id, start, end, cursor, page_size)
    if provider == "microsoft":
        return outlook_list(creds, start, end, cursor, page_size)
    raise CalendarServiceError(f"Unsupported provider: {provider}")


def get_event(account: CalendarAccount, event_id: str) -> dict:
    creds = account.external_account.credentials
    provider = account.external_account.provider
    if provider == "google":
        return google_get(creds, account.calendar_id, event_id)
    if provider == "microsoft":
        return outlook_get(creds, event_id)
    raise CalendarServiceError(f"Unsupported provider: {provider}")


def create_event(account: CalendarAccount, payload: dict) -> str:
    creds = account.external_account.credentials
    provider = account.external_account.provider
    if provider == "google":
        return google_create(creds, account.calendar_id, payload)
    if provider == "microsoft":
        return outlook_create(creds, payload)
    raise CalendarServiceError(f"Unsupported provider: {provider}")


def update_event(account: CalendarAccount, event_id: str, payload: dict) -> dict:
    creds = account.external_account.credentials
    provider = account.external_account.provider
    if provider == "google":
        return google_update(creds, account.calendar_id, event_id, payload)
    if provider == "microsoft":
        return outlook_update(creds, event_id, payload)
    raise CalendarServiceError(f"Unsupported provider: {provider}")


def delete_event(account: CalendarAccount, event_id: str) -> None:
    creds = account.external_account.credentials
    provider = account.external_account.provider
    if provider == "google":
        return google_delete(creds, account.calendar_id, event_id)
    if provider == "microsoft":
        return outlook_delete(creds, event_id)
    raise CalendarServiceError(f"Unsupported provider: {provider}")

