from __future__ import annotations

import logging
from zoneinfo import ZoneInfo

from celery import shared_task
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from moio_platform.settings import FLOWS_Q
from websockets_app.services.publisher import WebSocketEventPublisher

from .contracts import (
    apply_plan_patch,
    validate_instruction_payload,
    validate_llm_output_contract,
)
from .models import Robot, RobotEvent, RobotRun, RobotSession
from .robot_runtime import RobotRuntime
from .utils import is_within_operation_window

logger = logging.getLogger(__name__)

def _emit_event(
    *,
    robot: Robot,
    event_type: str,
    run: RobotRun | None = None,
    session: RobotSession | None = None,
    payload: dict | None = None,
) -> None:
    event = RobotEvent.objects.create(
        robot=robot,
        run=run,
        session=session,
        event_type=event_type,
        payload=payload or {},
    )
    if run is not None:
        tenant_id = str(robot.tenant_id) if robot.tenant_id else "public"
        WebSocketEventPublisher.publish_robot_run_event(
            tenant_id=tenant_id,
            robot_id=str(robot.id),
            run_id=str(run.id),
            event_type=event_type,
            payload={"event_id": str(event.id), **(payload or {})},
        )


def _resolve_operation_window(robot: Robot) -> tuple[bool, str]:
    window = robot.operation_window or {}
    if not window:
        return True, "no_window"

    start = window.get("start")
    end = window.get("end")
    tz_name = window.get("tz") or "UTC"
    if not start or not end:
        return True, "invalid_window_config_ignored"

    try:
        now_local = timezone.now().astimezone(ZoneInfo(tz_name))
        current_hhmm = now_local.strftime("%H:%M")
        is_open = is_within_operation_window(start_hhmm=start, end_hhmm=end, current_hhmm=current_hhmm)
        return is_open, f"window_{'open' if is_open else 'closed'}"
    except Exception:
        logger.warning("Invalid operation_window timezone, robot=%s", robot.id)
        return True, "invalid_timezone_ignored"


def _check_daily_run_limit(robot: Robot) -> tuple[bool, str]:
    limits = robot.rate_limits or {}
    max_daily_runs = limits.get("max_daily_runs")
    if not max_daily_runs:
        return True, "no_max_daily_runs"

    day_start = timezone.now().replace(hour=0, minute=0, second=0, microsecond=0)
    current_runs = RobotRun.objects.filter(robot=robot, started_at__gte=day_start).count()
    if current_runs >= int(max_daily_runs):
        return False, "max_daily_runs_exceeded"
    return True, "within_max_daily_runs"


def _check_daily_usage_limits(
    robot: Robot,
    *,
    additional_tokens: int = 0,
    additional_tool_calls: int = 0,
    additional_messages: int = 0,
) -> tuple[bool, str]:
    limits = robot.rate_limits or {}
    day_start = timezone.now().replace(hour=0, minute=0, second=0, microsecond=0)

    max_daily_tokens = limits.get("max_daily_tokens")
    max_daily_tool_calls = limits.get("max_daily_tool_calls")
    max_daily_messages_sent = limits.get("max_daily_messages_sent")

    if max_daily_tokens is not None:
        runs_today = RobotRun.objects.filter(robot=robot, started_at__gte=day_start).values_list("usage", flat=True)
        tokens_today = 0
        for usage in runs_today:
            if isinstance(usage, dict):
                tokens_today += int(usage.get("tokens") or 0)
        if tokens_today + additional_tokens > int(max_daily_tokens):
            return False, "max_daily_tokens_exceeded"

    if max_daily_tool_calls is not None:
        runs_today = RobotRun.objects.filter(robot=robot, started_at__gte=day_start).values_list("usage", flat=True)
        tool_calls_today = 0
        for usage in runs_today:
            if isinstance(usage, dict):
                tool_calls_today += int(usage.get("tool_calls") or 0)
        if tool_calls_today + additional_tool_calls > int(max_daily_tool_calls):
            return False, "max_daily_tool_calls_exceeded"

    if max_daily_messages_sent is not None:
        messages_today = RobotEvent.objects.filter(
            robot=robot,
            event_type="assistant.message",
            created_at__gte=day_start,
        ).count()
        if messages_today + additional_messages > int(max_daily_messages_sent):
            return False, "max_daily_messages_sent_exceeded"

    return True, "within_daily_usage_limits"


def _ensure_session(run: RobotRun) -> RobotSession:
    if run.session_id:
        return run.session

    requested_key = (run.trigger_payload or {}).get("session_key")
    source = (run.trigger_source or "manual").strip().lower()
    source_prefix = source if source in {"manual", "schedule", "event", "campaign"} else "manual"
    fallback_key = f"{source_prefix}:{run.id}"

    candidate_keys = [requested_key, fallback_key] if requested_key else [fallback_key]
    session: RobotSession | None = None
    for session_key in candidate_keys:
        try:
            session, _ = RobotSession.objects.get_or_create(
                robot=run.robot,
                session_key=session_key,
                defaults={
                    "run_id": run.id,
                    "metadata": {"created_by": "run_bootstrap"},
                    "transcript": [],
                    "intent_state": {},
                },
            )
            break
        except ValidationError:
            logger.warning("Invalid session_key provided; falling back. run=%s key=%s", run.id, session_key)
            continue

    if session is None:
        raise ValidationError("Could not create a valid RobotSession for this run")
    if session.run_id != run.id:
        session.run_id = run.id
        session.save(update_fields=["run_id", "updated_at"])

    run.session = session
    run.save(update_fields=["session"])
    return session


def _append_transcript_entries(
    session: RobotSession,
    user_text: str | None,
    assistant_text: str,
    tool_result: dict | None = None,
) -> None:
    entries = list(session.transcript or [])
    now_iso = timezone.now().isoformat()

    if user_text:
        entries.append({"role": "user", "content": user_text, "created_at": now_iso})
    if tool_result is not None:
        entries.append({"role": "tool", "content": tool_result, "created_at": now_iso})
    entries.append({"role": "assistant", "content": assistant_text, "created_at": now_iso})

    session.transcript = entries
    session.metadata = {
        **(session.metadata or {}),
        "updated_at": int(timezone.now().timestamp() * 1000),
        "transcript_entries": len(entries),
    }
    session.save(update_fields=["transcript", "metadata", "updated_at"])


def _estimate_tokens(transcript: list[dict]) -> int:
    char_count = 0
    for entry in transcript or []:
        content = entry.get("content")
        if isinstance(content, str):
            char_count += len(content)
        else:
            char_count += len(str(content))
    return max(1, char_count // 4)


def _compact_session(session: RobotSession, keep_last_n: int = 50) -> int:
    entries = list(session.transcript or [])
    if len(entries) <= keep_last_n:
        return 0
    dropped = entries[:-keep_last_n]
    summary = {
        "role": "system",
        "content": f"Compacted {len(dropped)} old entries",
        "created_at": timezone.now().isoformat(),
    }
    session.transcript = [summary] + entries[-keep_last_n:]
    session.metadata = {
        **(session.metadata or {}),
        "compaction_count": int((session.metadata or {}).get("compaction_count") or 0) + 1,
    }
    session.save(update_fields=["transcript", "metadata", "updated_at"])
    return 1


def _check_cancel_requested(run: RobotRun, robot: Robot, session: RobotSession) -> bool:
    # Cancellation can be requested by a concurrent API request; refresh before checking.
    run.refresh_from_db(fields=["cancel_requested_at", "status"])
    if not run.cancel_requested_at:
        return False
    if run.is_finished:
        return True
    run.status = RobotRun.STATUS_CANCELLED
    run.completed_at = timezone.now()
    run.error_data = {"message": "Run cancelled"}
    run.save(update_fields=["status", "completed_at", "error_data"])
    _emit_event(robot=robot, run=run, session=session, event_type="lifecycle.cancelled", payload={})
    return True


@shared_task(name="robots.tasks.execute_robot_run", queue=FLOWS_Q)
def execute_robot_run(run_id: str):
    run = RobotRun.objects.select_related("robot", "session").filter(id=run_id).first()
    if not run:
        logger.error("RobotRun not found: %s", run_id)
        return {"error": "run_not_found"}

    if run.is_finished:
        return {"status": run.status, "reason": "already_finished"}

    with transaction.atomic():
        run = RobotRun.objects.select_for_update().select_related("robot", "session").get(id=run_id)
        if run.is_finished:
            return {"status": run.status, "reason": "already_finished_locked"}
        if run.status == RobotRun.STATUS_RUNNING:
            return {"status": run.status, "reason": "already_running_locked"}
        run.status = RobotRun.STATUS_RUNNING
        run.save(update_fields=["status"])

    robot = run.robot
    session: RobotSession | None = None

    try:
        session = _ensure_session(run)

        _emit_event(
            robot=robot,
            run=run,
            session=session,
            event_type="lifecycle.started",
            payload={"run_id": str(run.id)},
        )

        if _check_cancel_requested(run, robot, session):
            return {"status": run.status}

        is_open, window_reason = _resolve_operation_window(robot)
        if not is_open:
            run.status = RobotRun.STATUS_CANCELLED
            run.completed_at = timezone.now()
            run.error_data = {"message": "Robot operation_window is closed", "reason": window_reason}
            run.save(update_fields=["status", "completed_at", "error_data"])
            _emit_event(robot=robot, run=run, session=session, event_type="lifecycle.cancelled", payload=run.error_data)
            return {"status": run.status}

        within_limit, limit_reason = _check_daily_run_limit(robot)
        if not within_limit:
            run.status = RobotRun.STATUS_FAILED
            run.completed_at = timezone.now()
            run.error_data = {"message": "Rate limit guard triggered", "reason": limit_reason}
            run.save(update_fields=["status", "completed_at", "error_data"])
            _emit_event(robot=robot, run=run, session=session, event_type="lifecycle.failed", payload=run.error_data)
            return {"status": run.status}

        payload = validate_instruction_payload(run.trigger_payload or {})
        runtime = RobotRuntime.for_robot(robot)

        usage = {
            "iterations": 0,
            "llm_calls": 0,
            "tool_calls": 0,
            "tokens": 0,
            "compactions_performed": 0,
        }
        max_iterations = int((robot.model_config or {}).get("max_iterations") or 3)
        compaction_cfg = robot.compaction_config or {}
        try:
            trigger_tokens = int(compaction_cfg.get("trigger_tokens") or 8000)
        except Exception:
            trigger_tokens = 8000
        try:
            keep_last_n = int(compaction_cfg.get("keep_last_n") or 50)
        except Exception:
            keep_last_n = 50
        try:
            max_entries_hard = int(compaction_cfg.get("max_entries_hard") or 2000)
        except Exception:
            max_entries_hard = 2000

        trigger_tokens = max(1, trigger_tokens)
        keep_last_n = max(1, keep_last_n)
        max_entries_hard = max(1, max_entries_hard)
        hard_keep_last_n = max(1, min(keep_last_n, max_entries_hard - 1)) if max_entries_hard > 1 else 1

        final_assistant_message = ""
        stop_reason = "completed"
        last_est_tokens_total = 0

        for iteration in range(1, max_iterations + 1):
            if _check_cancel_requested(run, robot, session):
                return {"status": run.status}

            if len(session.transcript or []) > max_entries_hard:
                performed = _compact_session(session, keep_last_n=hard_keep_last_n)
                usage["compactions_performed"] += performed
                if performed == 0:
                    # Defensive fallback: if compaction configuration is invalid, avoid crashing the run.
                    performed = _compact_session(session, keep_last_n=1)
                    usage["compactions_performed"] += performed

            est_tokens_total = _estimate_tokens(session.transcript or [])
            est_tokens_delta = max(0, est_tokens_total - last_est_tokens_total)
            last_est_tokens_total = est_tokens_total
            usage["tokens"] += est_tokens_delta
            if est_tokens_total >= trigger_tokens:
                usage["compactions_performed"] += _compact_session(session, keep_last_n=keep_last_n)

            llm_output, extracted_tool_calls = runtime.step(
                run=run,
                session=session,
                iteration=iteration,
                max_iterations=max_iterations,
                instruction_payload=payload,
            )
            llm_output = validate_llm_output_contract(llm_output)
            usage["iterations"] += 1
            usage["llm_calls"] += 1

            tool_calls = llm_output.get("tool_calls") or extracted_tool_calls or []
            allowed, usage_reason = _check_daily_usage_limits(
                robot,
                additional_tokens=usage["tokens"],
                additional_tool_calls=usage["tool_calls"] + len(tool_calls),
                additional_messages=1,
            )
            if not allowed:
                raise RuntimeError(f"Rate limit guard triggered: {usage_reason}")

            usage["tool_calls"] += len(tool_calls)
            tool_result = {"tool_calls": tool_calls} if tool_calls else None
            if tool_calls:
                _emit_event(
                    robot=robot,
                    run=run,
                    session=session,
                    event_type="tool.started",
                    payload={"iteration": iteration, "tool_calls": tool_calls},
                )
                _emit_event(
                    robot=robot,
                    run=run,
                    session=session,
                    event_type="tool.completed",
                    payload={"iteration": iteration, "tool_calls": tool_calls},
                )

            current_intent = session.intent_state or {}
            session.intent_state = apply_plan_patch(current_intent, llm_output.get("plan_patch"))
            session.save(update_fields=["intent_state", "updated_at"])

            final_assistant_message = llm_output["assistant_message"]
            stop_reason = llm_output["stop_reason"] or "completed"
            _emit_event(
                robot=robot,
                run=run,
                session=session,
                event_type="assistant.message",
                payload={"iteration": iteration, "message": final_assistant_message},
            )
            _append_transcript_entries(
                session=session,
                user_text=payload.get("instruction") if iteration == 1 else None,
                assistant_text=final_assistant_message,
                tool_result=tool_result,
            )
            _emit_event(
                robot=robot,
                run=run,
                session=session,
                event_type="metrics",
                payload={"iteration": iteration, "usage": usage},
            )
            if stop_reason != "continue":
                break

        run.usage = usage
        run.output_data = {"assistant_message": final_assistant_message, "stop_reason": stop_reason}
        run.execution_context = {
            **(run.execution_context or {}),
            "window_check": window_reason,
            "limit_check": limit_reason,
            "effective_instruction": payload,
            "completed_at": timezone.now().isoformat(),
        }
        run.status = RobotRun.STATUS_SUCCESS
        run.completed_at = timezone.now()
        run.save(
            update_fields=["usage", "output_data", "execution_context", "status", "completed_at"]
        )
        _emit_event(
            robot=robot,
            run=run,
            session=session,
            event_type="lifecycle.completed",
            payload={"status": run.status, "usage": run.usage},
        )
        return {"status": run.status, "output": run.output_data}
    except (ValidationError, Exception) as exc:
        logger.exception("Robot run failed: %s", run.id)
        run.status = RobotRun.STATUS_FAILED
        run.completed_at = timezone.now()
        run.error_data = {"message": str(exc), "type": exc.__class__.__name__}
        run.save(update_fields=["status", "completed_at", "error_data"])
        _emit_event(
            robot=robot,
            run=run,
            session=session,
            event_type="lifecycle.failed",
            payload=run.error_data,
        )
        return {"status": run.status, "error": run.error_data}


@shared_task(name="robots.tasks.cancel_robot_run", queue=FLOWS_Q)
def cancel_robot_run(run_id: str):
    run = RobotRun.objects.select_related("robot", "session").filter(id=run_id).first()
    if not run:
        return {"error": "run_not_found"}
    if run.is_finished:
        return {"status": run.status, "reason": "already_finished"}

    already_requested = bool(run.cancel_requested_at)
    if not already_requested:
        run.cancel_requested_at = timezone.now()
        run.save(update_fields=["cancel_requested_at"])

    _emit_event(
        robot=run.robot,
        run=run,
        session=run.session if run.session_id else None,
        event_type="lifecycle.cancel_requested",
        payload={"cancel_requested_at": run.cancel_requested_at.isoformat() if run.cancel_requested_at else None},
    )
    return {
        "status": "already_requested" if already_requested else "cancel_requested",
        "run_id": str(run.id),
    }


@shared_task(name="robots.tasks.execute_scheduled_robot", queue=FLOWS_Q)
def execute_scheduled_robot(robot_id: str):
    robot = Robot.objects.filter(id=robot_id, enabled=True).first()
    if not robot:
        return {"error": "robot_not_found_or_disabled"}

    is_open, reason = _resolve_operation_window(robot)
    if not is_open:
        return {"status": "skipped", "reason": reason}

    run = RobotRun.objects.create(
        robot=robot,
        status=RobotRun.STATUS_PENDING,
        trigger_source="schedule",
        trigger_payload={"instruction_schema_version": 1, "instruction": "", "metadata": {"scheduled": True}},
    )
    execute_robot_run.apply_async(args=[str(run.id)])
    return {"status": "enqueued", "run_id": str(run.id)}
