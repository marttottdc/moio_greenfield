#!/usr/bin/env python3
"""
Standalone script to test the capture -> classify -> proposed activity flow
outside the Django project. No Django or DB; uses only openai + pydantic.

Usage:
  export OPENAI_API_KEY=sk-...
  python scripts/standalone_capture_to_activity.py "Call John tomorrow 3pm re quote"
  python scripts/standalone_capture_to_activity.py "Meeting with Jane next Monday 10am-11am" --anchor contact --anchor-id abc-123

Requirements: pip install openai pydantic
"""

from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass
from datetime import datetime, timezone as dt_timezone
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field, ConfigDict


# -----------------------------------------------------------------------------
# Contract (mirror of crm/core/activity_capture_contract.py)
# -----------------------------------------------------------------------------


class CreateTaskIntent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    do: bool
    title: Optional[str] = None
    due_at: Optional[str] = None
    owner: Optional[str] = None
    priority: Optional[Literal["LOW", "MEDIUM", "HIGH"]] = None


class AttendeeItem(BaseModel):
    model_config = ConfigDict(extra="forbid")
    email: Optional[str] = None
    address: Optional[str] = None


class CreateAppointmentIntent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    do: bool
    title: Optional[str] = None
    start_at: Optional[str] = None
    end_at: Optional[str] = None
    attendees: list[AttendeeItem] = Field(default_factory=list)
    location: Optional[str] = None
    book_calendar: bool = False


class IntentOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    create_task: CreateTaskIntent = Field(default_factory=lambda: CreateTaskIntent(do=False))
    create_appointment: CreateAppointmentIntent = Field(
        default_factory=lambda: CreateAppointmentIntent(do=False)
    )


class SuggestLinkItem(BaseModel):
    model_config = ConfigDict(extra="forbid")
    type: Optional[str] = None
    id: Optional[str] = None
    label: Optional[str] = None


class ClassificationOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    summary: str
    channel: Literal["PHONE", "EMAIL", "WHATSAPP", "VISIT", "IN_PERSON", "WEB", "SMS", "OTHER"]
    direction: Literal["INBOUND", "OUTBOUND", "INTERNAL"]
    outcome: Literal["CONNECTED", "NO_ANSWER", "LEFT_MESSAGE", "SENT", "RECEIVED", "UNKNOWN"]
    intent: IntentOutput
    suggest_links: list[SuggestLinkItem] = Field(default_factory=list)
    needs_review: bool
    review_reasons: list[str] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0)


# -----------------------------------------------------------------------------
# Helpers (mirror of crm/services/activity_capture_service.py logic, no Django)
# -----------------------------------------------------------------------------


def _parse_iso_dt(value: Optional[str], *, user_tz: str) -> Optional[datetime]:
    if not value:
        return None
    raw = str(value).strip()
    if not raw:
        return None
    try:
        if raw.endswith("Z"):
            raw = raw[:-1] + "+00:00"
        dt = datetime.fromisoformat(raw)
    except Exception:
        return None
    if dt.tzinfo is None:
        try:
            from zoneinfo import ZoneInfo
            dt = dt.replace(tzinfo=ZoneInfo(user_tz))
        except Exception:
            dt = dt.replace(tzinfo=dt_timezone.utc)
    return dt


def build_system_prompt(
    *,
    tenant_name: str,
    current_utc_iso: str,
    user_tz: str,
    anchor_model: str,
    anchor_label: str,
    anchor_id: str,
    raw_text: str,
) -> str:
    return (
        "You are Moio, a precise CRM activity classifier for {tenant_name}.\n"
        "Current server time (UTC): {current_utc_iso}\n"
        "User timezone: {user_tz}\n"
        "Anchor record: {anchor_model} \"{anchor_label}\" (ID: {anchor_id})\n\n"
        "Classify the sales note below. Resolve relative dates/times into full ISO strings using the user's timezone.\n"
        "If any date/time or entity is ambiguous, set needs_review=true and list clear reasons.\n"
        "Output ONLY valid JSON matching the ClassificationOutput schema.\n\n"
        "Sales note:\n"
        "\"\"\"{raw_text}\"\"\"\n"
    ).format(
        tenant_name=tenant_name,
        current_utc_iso=current_utc_iso,
        user_tz=user_tz,
        anchor_model=anchor_model,
        anchor_label=anchor_label,
        anchor_id=anchor_id,
        raw_text=raw_text,
    )


def build_proposed_activity(
    *,
    raw_text: str,
    classification: dict[str, Any],
    user_tz: str,
) -> dict[str, Any]:
    """Build proposed activity dict from classification (no DB)."""
    intent = (classification.get("intent") or {}) if isinstance(classification.get("intent"), dict) else {}
    summary = (classification.get("summary") or "").strip() or (raw_text or "")[:500]
    create_task = intent.get("create_task") if isinstance(intent.get("create_task"), dict) else None
    create_appt = intent.get("create_appointment") if isinstance(intent.get("create_appointment"), dict) else None

    if create_task and create_task.get("do") is True:
        due_at = _parse_iso_dt(create_task.get("due_at"), user_tz=user_tz)
        title = (create_task.get("title") or summary or "").strip() or "Follow-up"
        return {
            "kind": "task",
            "title": title,
            "due_at": due_at.isoformat() if due_at else None,
            "priority": create_task.get("priority") or "MEDIUM",
            "description": summary or raw_text,
        }

    if create_appt and create_appt.get("do") is True:
        start_at = _parse_iso_dt(create_appt.get("start_at"), user_tz=user_tz)
        end_at = _parse_iso_dt(create_appt.get("end_at"), user_tz=user_tz)
        title = (create_appt.get("title") or summary or "").strip() or "Meeting"
        return {
            "kind": "event",
            "title": title,
            "start_at": start_at.isoformat() if start_at else None,
            "end_at": end_at.isoformat() if end_at else None,
            "location": create_appt.get("location"),
            "attendees": create_appt.get("attendees") or [],
        }

    title = (summary or "Note").strip() or "Note"
    return {
        "kind": "note",
        "title": title,
        "body": raw_text or summary,
    }


# -----------------------------------------------------------------------------
# OpenAI classify (standalone: env OPENAI_API_KEY, model gpt-4o-mini)
# -----------------------------------------------------------------------------


def classify_raw_text(
    raw_text: str,
    *,
    api_key: Optional[str] = None,
    model: str = "gpt-4o-mini",
    tenant_name: str = "Test Tenant",
    user_tz: str = "UTC",
    anchor_model: str = "crm.contact",
    anchor_label: str = "Contact",
    anchor_id: str = "standalone",
) -> ClassificationOutput:
    from openai import OpenAI

    key = api_key or os.environ.get("OPENAI_API_KEY")
    if not key:
        raise RuntimeError("Set OPENAI_API_KEY or pass api_key=")

    now_utc = datetime.now(dt_timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    prompt = build_system_prompt(
        tenant_name=tenant_name,
        current_utc_iso=now_utc,
        user_tz=user_tz,
        anchor_model=anchor_model,
        anchor_label=anchor_label,
        anchor_id=anchor_id,
        raw_text=raw_text,
    )

    client = OpenAI(api_key=key)

    # Prefer Responses API if available, else Completions.
    try:
        resp = client.responses.parse(
            model=model,
            instructions=prompt,
            input="",
            text_format=ClassificationOutput,
        )
        parsed = getattr(resp, "output_parsed", None)
        if parsed is not None:
            return parsed
        raw = getattr(resp, "output_text", None)
        if raw:
            return ClassificationOutput.model_validate(json.loads(raw))
    except AttributeError:
        pass
    except Exception:
        pass

    # Fallback: Chat Completions structured parse
    resp = client.beta.chat.completions.parse(
        model=model,
        messages=[
            {"role": "system", "content": prompt},
            {"role": "user", "content": ""},
        ],
        response_format=ClassificationOutput,
    )
    msg = resp.choices[0].message
    parsed = getattr(msg, "parsed", None)
    if parsed is not None:
        return parsed
    content = getattr(msg, "content", None)
    if content:
        return ClassificationOutput.model_validate(json.loads(content))
    raise RuntimeError("No parsed output from OpenAI")


# -----------------------------------------------------------------------------
# CLI
# -----------------------------------------------------------------------------


def main() -> None:
    args = sys.argv[1:]
    if not args:
        print("Usage: python scripts/standalone_capture_to_activity.py \"<sales note>\" [--anchor contact] [--anchor-id ID]")
        print("  e.g. python scripts/standalone_capture_to_activity.py \"Call John tomorrow 3pm re quote\"")
        sys.exit(1)

    anchor_model = "crm.contact"
    anchor_id = "standalone"
    parts = []
    i = 0
    while i < len(args):
        if args[i] == "--anchor" and i + 1 < len(args):
            anchor_model = args[i + 1]
            i += 2
            continue
        if args[i] == "--anchor-id" and i + 1 < len(args):
            anchor_id = args[i + 1]
            i += 2
            continue
        parts.append(args[i])
        i += 1
    raw_text = " ".join(parts).strip()
    if not raw_text:
        print("Error: provide a non-empty sales note.")
        sys.exit(1)

    print("Classifying...")
    try:
        out = classify_raw_text(
            raw_text,
            anchor_model=anchor_model,
            anchor_label=anchor_id,
            anchor_id=anchor_id,
        )
    except Exception as e:
        print("Error:", e)
        sys.exit(2)

    classification = out.model_dump()
    proposed = build_proposed_activity(
        raw_text=raw_text,
        classification=classification,
        user_tz="UTC",
    )

    print("\n--- Classification ---")
    print(json.dumps(classification, indent=2, default=str))
    print("\n--- Proposed activity (would create) ---")
    print(json.dumps(proposed, indent=2, default=str))


if __name__ == "__main__":
    main()
