"""Celery tasks for executing flow scripts in an isolated subprocess."""
from __future__ import annotations

import base64
import json
import subprocess
import sys
import textwrap
from typing import Any, Dict

from celery import shared_task
from django.conf import settings
from django.db import transaction
from moio_platform.settings import FLOWS_Q
from django.utils import timezone

from ..models import FlowScriptLog, FlowScriptRun

_RUNNER_TEMPLATE = textwrap.dedent(
    """\
import base64
import json
import sys
import traceback

SAFE_BUILTINS = {
    'abs': abs,
    'all': all,
    'any': any,
    'bool': bool,
    'dict': dict,
    'enumerate': enumerate,
    'float': float,
    'int': int,
    'len': len,
    'list': list,
    'max': max,
    'min': min,
    'range': range,
    'round': round,
    'set': set,
    'sorted': sorted,
    'str': str,
    'sum': sum,
    'tuple': tuple,
    'zip': zip,
}

def emit(payload):
    sys.stdout.write(json.dumps(payload, default=str))
    sys.stdout.write(chr(10))
    sys.stdout.flush()

encoded = sys.argv[1]
params_raw = sys.argv[2]
code = base64.b64decode(encoded.encode('utf-8')).decode('utf-8')
params = json.loads(params_raw)

def log(message=None, **details):
    emit({'type': 'log', 'level': 'info', 'message': message or '', 'details': details})

def safe_print(*args, **kwargs):
    message = ' '.join(str(arg) for arg in args)
    emit({'type': 'log', 'level': 'info', 'message': message, 'details': {}})

namespace = {
    '__name__': '__main__',
    '__builtins__': SAFE_BUILTINS,
    'log': log,
    'print': safe_print,
    'PARAMS': params,
}

try:
    exec(compile(code, '<script>', 'exec'), namespace, namespace)
    fn = namespace.get('main') or namespace.get('run')
    result = None
    if callable(fn):
        result = fn(params)
    elif 'RESULT' in namespace:
        result = namespace['RESULT']
    elif 'result' in namespace:
        result = namespace['result']
    emit({'type': 'result', 'result': result})
except Exception as exc:  # noqa: BLE001 - surfacing script errors
    emit({'type': 'error', 'error': str(exc), 'traceback': traceback.format_exc()})
    sys.exit(1)
    """
)


class ScriptExecutionError(Exception):
    """Raised when a script execution fails."""

    def __init__(self, payload: Dict[str, Any]):
        super().__init__(payload.get('error') or 'Script execution failed')
        self.payload = payload


def _coerce_jsonable(value: Any) -> Any:
    try:
        json.dumps(value)
        return value
    except TypeError:
        if isinstance(value, dict):
            return {str(k): _coerce_jsonable(v) for k, v in value.items()}
        if isinstance(value, (list, tuple, set)):
            return [_coerce_jsonable(v) for v in value]
        if value is None:
            return None
        return str(value)


def _execute_in_subprocess(run: FlowScriptRun) -> Dict[str, Any]:
    """Execute the script version associated with ``run`` inside a subprocess."""

    encoded = base64.b64encode(run.version.code.encode("utf-8")).decode("utf-8")
    params = json.dumps(run.input_payload or {}, default=str)
    process = subprocess.Popen(
        [sys.executable, "-u", "-c", _RUNNER_TEMPLATE, encoded, params],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        assert process.stdout is not None
        for raw in process.stdout:
            raw = raw.strip()
            if not raw:
                continue
            try:
                payload = json.loads(raw)
            except json.JSONDecodeError:
                FlowScriptLog.objects.create(
                    run=run,
                    tenant=run.tenant,
                    level=FlowScriptLog.LEVEL_WARNING,
                    message="Unstructured output",
                    details={"payload": raw},
                )
                continue
            event_type = payload.get("type")
            if event_type == "log":
                FlowScriptLog.objects.create(
                    run=run,
                    tenant=run.tenant,
                    level=payload.get("level", FlowScriptLog.LEVEL_INFO),
                    message=str(payload.get("message", "")),
                    details=payload.get("details") or {},
                )
            elif event_type == "result":
                try:
                    process.wait(timeout=1)
                except subprocess.TimeoutExpired:
                    process.terminate()
                return {
                    "status": FlowScriptRun.STATUS_SUCCESS,
                    "result": payload.get("result"),
                }
            elif event_type == "error":
                raise ScriptExecutionError(payload)
        stderr_data = process.stderr.read() if process.stderr else ""
        returncode = process.wait()
        if returncode != 0:
            raise ScriptExecutionError({"error": stderr_data or "Process exited with error."})
    finally:
        if process.stdout:
            process.stdout.close()
        if process.stderr:
            process.stderr.close()
    return {
        "status": FlowScriptRun.STATUS_SUCCESS,
        "result": None,
    }


@shared_task(name="flows.scripts.execute_script_run", queue=FLOWS_Q)
def execute_script_run(run_id: str) -> None:
    """Execute a ``FlowScriptRun`` asynchronously."""

    run = FlowScriptRun.objects.select_related("version", "tenant", "script").get(
        id=run_id
    )
    if run.status not in {
        FlowScriptRun.STATUS_PENDING,
        FlowScriptRun.STATUS_RUNNING,
    }:
        return

    with transaction.atomic():
        run.status = FlowScriptRun.STATUS_RUNNING
        run.save(update_fields=["status"])
        FlowScriptLog.objects.create(
            run=run,
            tenant=run.tenant,
            level=FlowScriptLog.LEVEL_INFO,
            message="Run started.",
        )

    started_at = timezone.now()
    try:
        outcome = _execute_in_subprocess(run)
        run.output_payload = _coerce_jsonable(outcome.get("result")) or {}
        run.error_payload = {}
        run.status = outcome.get("status", FlowScriptRun.STATUS_SUCCESS)
    except ScriptExecutionError as exc:
        run.status = FlowScriptRun.STATUS_FAILED
        run.error_payload = _coerce_jsonable(exc.payload)
        FlowScriptLog.objects.create(
            run=run,
            tenant=run.tenant,
            level=FlowScriptLog.LEVEL_ERROR,
            message=str(exc),
            details=exc.payload,
        )
    except Exception as exc:  # noqa: BLE001 - surfacing unexpected errors
        run.status = FlowScriptRun.STATUS_FAILED
        run.error_payload = {"error": str(exc)}
        FlowScriptLog.objects.create(
            run=run,
            tenant=run.tenant,
            level=FlowScriptLog.LEVEL_ERROR,
            message="Unexpected error during execution.",
            details={"error": str(exc)},
        )
    finally:
        run.completed_at = timezone.now()
        run.save(update_fields=["status", "output_payload", "error_payload", "completed_at"])
        FlowScriptLog.objects.create(
            run=run,
            tenant=run.tenant,
            level=FlowScriptLog.LEVEL_INFO,
            message="Run finished.",
            details={
                "status": run.status,
                "duration_ms": run.duration_ms,
            },
        )

    if getattr(settings, "FLOW_SCRIPTS_NOTIFY_ON_SUCCESS", False) and run.status == FlowScriptRun.STATUS_SUCCESS:
        FlowScriptLog.objects.create(
            run=run,
            tenant=run.tenant,
            level=FlowScriptLog.LEVEL_INFO,
            message="Execution completed successfully.",
        )
