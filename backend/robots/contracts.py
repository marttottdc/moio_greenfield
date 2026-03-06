from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timedelta, timezone as dt_timezone
from typing import Any

from django.core.exceptions import ValidationError
from django.utils import timezone


ALLOWED_INSTRUCTION_KEYS = {
    "instruction_schema_version",
    "instruction",
    "objective_override",
    "queue_items",
    "constraints",
    "metadata",
    "session_key",
    "trigger_source",
    # Optional test-only key for local deterministic runs.
    "llm_output",
}


def validate_instruction_payload(payload: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise ValidationError("trigger_payload must be a JSON object")

    unknown = sorted(set(payload.keys()) - ALLOWED_INSTRUCTION_KEYS)
    if unknown:
        raise ValidationError(f"Unknown trigger_payload keys: {', '.join(unknown)}")

    normalized = {
        "instruction_schema_version": int(payload.get("instruction_schema_version", 1)),
        "instruction": payload.get("instruction", "") or "",
        "objective_override": payload.get("objective_override") or {},
        "queue_items": payload.get("queue_items") or [],
        "constraints": payload.get("constraints") or {},
        "metadata": payload.get("metadata") or {},
        "session_key": payload.get("session_key"),
        "trigger_source": payload.get("trigger_source"),
    }
    if "llm_output" in payload:
        normalized["llm_output"] = payload["llm_output"]

    if not isinstance(normalized["instruction"], str):
        raise ValidationError("instruction must be a string")
    if not isinstance(normalized["objective_override"], dict):
        raise ValidationError("objective_override must be an object")
    if not isinstance(normalized["queue_items"], list):
        raise ValidationError("queue_items must be an array")
    if not isinstance(normalized["constraints"], dict):
        raise ValidationError("constraints must be an object")
    if not isinstance(normalized["metadata"], dict):
        raise ValidationError("metadata must be an object")
    if normalized["session_key"] is not None and not isinstance(normalized["session_key"], str):
        raise ValidationError("session_key must be a string")

    return normalized


def validate_llm_output_contract(output: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(output, dict):
        raise ValidationError("LLM output must be a JSON object")

    required = {"assistant_message", "tool_calls", "plan_patch", "stop_reason"}
    missing = sorted(required - set(output.keys()))
    if missing:
        raise ValidationError(f"LLM output missing required keys: {', '.join(missing)}")

    if not isinstance(output.get("assistant_message"), str):
        raise ValidationError("assistant_message must be a string")
    if not isinstance(output.get("tool_calls"), list):
        raise ValidationError("tool_calls must be an array")
    if output.get("plan_patch") is not None and not isinstance(output.get("plan_patch"), dict):
        raise ValidationError("plan_patch must be an object or null")
    if not isinstance(output.get("stop_reason"), str):
        raise ValidationError("stop_reason must be a string")

    return output


def _deep_merge(base: dict[str, Any], patch: dict[str, Any]) -> dict[str, Any]:
    result = deepcopy(base)
    for key, value in patch.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def _parse_iso_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if timezone.is_naive(parsed):
            parsed = parsed.replace(tzinfo=dt_timezone.utc)
        return parsed
    except Exception:
        return None


def _coerce_int(value: Any, *, field_name: str, default: int | None = None) -> int:
    if value is None or value == "":
        if default is None:
            raise ValidationError(f"{field_name} must be an integer")
        return default
    try:
        return int(value)
    except Exception:
        raise ValidationError(f"{field_name} must be an integer")


def apply_plan_patch(previous_state: dict[str, Any], patch: dict[str, Any] | None) -> dict[str, Any]:
    prev = deepcopy(previous_state or {})
    if not patch:
        return prev

    next_state = _deep_merge(prev, patch)

    prev_cursor = _coerce_int(((prev.get("queue") or {}).get("cursor")), field_name="queue.cursor", default=0)
    next_cursor = _coerce_int(
        ((next_state.get("queue") or {}).get("cursor")), field_name="queue.cursor", default=0
    )
    if next_cursor < prev_cursor:
        raise ValidationError("RobotPlan invariant failed: queue.cursor must be monotonic")

    queue = next_state.get("queue") or {}
    items = queue.get("items") or []
    current = next_state.get("current") or {}
    current_item_id = current.get("item_id")
    if current_item_id and items:
        item_ids: set[str] = set()
        for item in items:
            if isinstance(item, dict):
                if item.get("id") is not None:
                    item_ids.add(str(item.get("id")))
                elif item.get("item_id") is not None:
                    item_ids.add(str(item.get("item_id")))
            else:
                item_ids.add(str(item))
        if item_ids:
            if str(current_item_id) not in item_ids:
                raise ValidationError("RobotPlan invariant failed: current.item_id must belong to queue.items")
        else:
            # Best-effort fallback for unexpected item shapes.
            if current_item_id not in items:
                raise ValidationError("RobotPlan invariant failed: current.item_id must belong to queue.items")

    attempt = _coerce_int(current.get("attempt"), field_name="current.attempt", default=0)
    if attempt > 5:
        raise ValidationError("RobotPlan invariant failed: current.attempt exceeds max allowed")

    prev_budgets = prev.get("budgets") or {}
    next_budgets = next_state.get("budgets") or {}
    for budget_key in ("daily_messages_remaining", "daily_tokens_remaining"):
        prev_val = prev_budgets.get(budget_key)
        next_val = next_budgets.get(budget_key)
        if prev_val is None or next_val is None:
            continue
        prev_int = _coerce_int(prev_val, field_name=f"budgets.{budget_key}")
        next_int = _coerce_int(next_val, field_name=f"budgets.{budget_key}")
        if next_int > prev_int:
            raise ValidationError(
                f"RobotPlan invariant failed: {budget_key} cannot increase inside a run"
            )

    blocked_until = ((next_state.get("state") or {}).get("blocked_until"))
    blocked_dt = _parse_iso_datetime(blocked_until)
    if blocked_dt and blocked_dt > timezone.now() + timedelta(days=30):
        raise ValidationError("RobotPlan invariant failed: blocked_until exceeds max allowed delay window")

    return next_state
