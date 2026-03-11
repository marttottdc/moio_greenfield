#!/usr/bin/env python3
"""
Standalone script to test the capture -> classify -> suggested activities flow
outside the Django project. No Django or DB; uses only openai + pydantic.

Uses the same prompt and schema as crm/services/activity_capture_service.py
(build_activity_suggestion_prompt + ClassificationOutput with suggested_activities).

Usage:
  export OPENAI_API_KEY=sk-...
  python scripts/standalone_capture_to_activity.py "Call John tomorrow 3pm re quote"
  python scripts/standalone_capture_to_activity.py "Tuve una llamada con Carlos, quedamos en revisar la presentación"
  python scripts/standalone_capture_to_activity.py "Meeting with Jane next Monday" --anchor contact --anchor-id abc-123 --lang en

Requirements: pip install openai pydantic
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone as dt_timezone
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field, ConfigDict


# -----------------------------------------------------------------------------
# Contract (mirror of crm/core/activity_capture_contract.py)
# -----------------------------------------------------------------------------


class SuggestedActivityItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["task", "event", "deal"]
    title: str
    description: Optional[str] = None
    proposed_due_at: Optional[str] = None
    priority: Optional[Literal["LOW", "MEDIUM", "HIGH"]] = None
    proposed_start_at: Optional[str] = None
    proposed_end_at: Optional[str] = None
    location: Optional[str] = None
    attendees: list[str] = Field(default_factory=list)
    status: Optional[Literal["planned", "completed"]] = None
    proposed_value: Optional[str] = None
    proposed_currency: Optional[str] = None
    needs_time_confirmation: bool = False
    reason: Optional[str] = None


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

    suggested_activities: list[SuggestedActivityItem] = Field(default_factory=list)
    temporal_type: Literal["past", "future", "ambiguous"] = "ambiguous"
    temporal_reasoning: Optional[str] = None
    suggest_links: list[SuggestLinkItem] = Field(default_factory=list)
    needs_review: bool
    review_reasons: list[str] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0)


# -----------------------------------------------------------------------------
# Prompt (mirror of build_activity_suggestion_prompt from activity_capture_service.py)
# -----------------------------------------------------------------------------


def build_activity_suggestion_prompt(
    *,
    tenant_name: str,
    current_utc_iso: str,
    user_tz: str,
    user_lang: str,
    anchor_model: str,
    anchor_label: str,
    anchor_id: str,
    raw_text: str,
) -> str:
    lang_names = {"es": "Spanish", "en": "English", "pt": "Portuguese", "fr": "French"}
    lang_label = lang_names.get(user_lang.split("-")[0].lower(), "English")
    return (
        "You are Moio, a helpful activity suggester for the CRM of {tenant_name}.\n"
        "Current server time (UTC): {current_utc_iso}\n"
        "User timezone: {user_tz}\n"
        "User language: {user_lang} ({lang_label}). Output all titles, descriptions, reasons in {lang_label}.\n"
        "Anchor record: {anchor_model} \"{anchor_label}\" (ID: {anchor_id})\n\n"
        "TASK: Read the sales note and suggest activities to register in the CRM.\n"
        "Put ALL activities in suggested_activities—this is the ONLY output for activities. One item per activity.\n\n"
        "Activity kinds (use exactly these):\n"
        "- kind 'event': Interactions with contacts (calls, meetings, coffees, visits, messages). Past: status='completed'. Future: status='planned'.\n"
        "  Use proposed_start_at / proposed_end_at. If time vague → needs_time_confirmation=true.\n"
        "- kind 'task': Internal work (prepare presentation, update quote, send docs, review internally).\n"
        "  Use proposed_due_at (usually 1 day before any related meeting if applicable).\n"
        "- kind 'deal': Business opportunity (potential projects, interest in buying, negotiation, possible sale).\n"
        "  Optional: proposed_value (number), proposed_currency (3-letter code).\n\n"
        "Rules:\n"
        "1. Always include a completed 'event' for any past interaction mentioned.\n"
        "2. If a follow-up meeting/review is agreed → add a planned 'event'.\n"
        "3. If preparation is implied (presentation, quote, docs to review/show) → add a 'task' with due before the meeting.\n"
        "4. If multiple opportunities/projects mentioned (e.g. 'two possible projects') → create separate 'deal' for each (title like 'Proyecto 1 - [Contacto]', 'Proyecto 2 - [Contacto]'), leave value null, description with 'Pendiente de detalles'.\n"
        "5. Suggest a follow-up 'event' (planned, ~7 days ahead, needs_time_confirmation=true) when momentum exists but no date set.\n"
        "6. Resolve relative dates to ISO-8601 in {user_tz} (hoy=today, la semana próxima=next week approx, próximo lunes=next Monday).\n"
        "7. List EVERY activity in suggested_activities—past events, tasks, future events, deals. Do not omit any.\n\n"
        "Examples:\n\n"
        "Input: 'Tuve una llamada con Carlos López, quedamos en revisar una presentación sobre el avance del proyecto la semana que viene'\n"
        "→ 3 activities: completed event (llamada), task (preparar presentación), planned event (revisión)\n\n"
        "Input: 'tomé un cafe con Carla Velez, acordamos juntarnos para revisar la cotizacion el proximo lunes'\n"
        "→ completed event (café), task (preparar cotización), planned event (revisión lunes)\n\n"
        "Input: 'fui a ver a Gustavo Molina, me comentó que tiene dos posibles proyectos'\n"
        "→ completed event (visita), two separate deals (Proyecto 1 & Proyecto 2), planned event (seguimiento ~7 días)\n\n"
        "Think step by step internally before outputting:\n"
        "- What past interactions?\n"
        "- Any agreed future meeting?\n"
        "- Any preparation needed?\n"
        "- Any business opportunities?\n"
        "- How many deals if multiple?\n"
        "Then output only the JSON.\n\n"
        "The sales note is provided as the user input."
    ).format(
        tenant_name=tenant_name,
        current_utc_iso=current_utc_iso,
        user_tz=user_tz,
        user_lang=user_lang,
        lang_label=lang_label,
        anchor_model=anchor_model,
        anchor_label=anchor_label,
        anchor_id=anchor_id,
    )


# -----------------------------------------------------------------------------
# Build proposed activities from suggested_activities (no DB)
# -----------------------------------------------------------------------------


def build_proposed_activities(
    *,
    classification: dict[str, Any],
) -> list[dict[str, Any]]:
    """Convert suggested_activities to proposed activity dicts (would create in CRM)."""
    suggested = classification.get("suggested_activities")
    if not isinstance(suggested, list):
        return []

    out = []
    for item in suggested:
        if not isinstance(item, dict):
            continue
        kind = (item.get("kind") or "event").lower()
        if kind not in ("task", "event", "deal"):
            continue
        proposed = {
            "kind": kind,
            "title": (item.get("title") or "").strip() or "Activity",
            "description": item.get("description"),
            "status": item.get("status") or "planned",
            "reason": item.get("reason"),
            "needs_time_confirmation": bool(item.get("needs_time_confirmation")),
        }
        if kind == "task":
            proposed["due_at"] = item.get("proposed_due_at")
            proposed["priority"] = item.get("priority") or "MEDIUM"
        elif kind == "event":
            proposed["start_at"] = item.get("proposed_start_at")
            proposed["end_at"] = item.get("proposed_end_at")
            proposed["location"] = item.get("location")
            proposed["attendees"] = item.get("attendees") or []
        elif kind == "deal":
            proposed["proposed_value"] = item.get("proposed_value")
            proposed["proposed_currency"] = item.get("proposed_currency") or "USD"
        out.append(proposed)
    return out


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
    user_lang: str = "es",
    anchor_model: str = "crm.contact",
    anchor_label: str = "Contact",
    anchor_id: str = "standalone",
) -> ClassificationOutput:
    from openai import OpenAI

    key = api_key or os.environ.get("OPENAI_API_KEY")
    if not key:
        raise RuntimeError("Set OPENAI_API_KEY or pass api_key=")

    now_utc = datetime.now(dt_timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    prompt = build_activity_suggestion_prompt(
        tenant_name=tenant_name,
        current_utc_iso=now_utc,
        user_tz=user_tz,
        user_lang=user_lang,
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
            input=raw_text or " ",
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
            {"role": "user", "content": raw_text or ""},
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
        print("Usage: python scripts/standalone_capture_to_activity.py \"<sales note>\" [options]")
        print("  --anchor MODEL    anchor_model (default: crm.contact)")
        print("  --anchor-id ID    anchor_id (default: standalone)")
        print("  --lang LANG       user language (default: es)")
        print()
        print("Example: python scripts/standalone_capture_to_activity.py \"Tuve una llamada con Carlos\"")
        sys.exit(1)

    anchor_model = "crm.contact"
    anchor_id = "standalone"
    user_lang = "es"
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
        if args[i] == "--lang" and i + 1 < len(args):
            user_lang = args[i + 1]
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
            user_lang=user_lang,
        )
    except Exception as e:
        print("Error:", e)
        sys.exit(2)

    classification = out.model_dump()
    proposed = build_proposed_activities(classification=classification)

    print("\n--- Classification ---")
    print(json.dumps(classification, indent=2, default=str))
    print("\n--- Suggested activities (would create in CRM) ---")
    print(json.dumps(proposed, indent=2, default=str))


if __name__ == "__main__":
    main()
