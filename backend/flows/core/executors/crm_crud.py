from __future__ import annotations

from copy import deepcopy
from typing import Any, Dict

from jsonschema import Draft202012Validator

from crm.contracts import get_resource
from flows.core.lib import render_template_string


class CrmCrudError(ValueError):
    pass


def _render_templates(value: Any, *, payload: Any, ctx: dict) -> Any:
    if isinstance(value, str):
        return render_template_string(value, payload, ctx)
    if isinstance(value, list):
        return [_render_templates(v, payload=payload, ctx=ctx) for v in value]
    if isinstance(value, dict):
        return {k: _render_templates(v, payload=payload, ctx=ctx) for k, v in value.items()}
    return value


def _validate_jsonschema(schema: dict, data: Any, *, label: str) -> None:
    try:
        Draft202012Validator(schema).validate(data)
    except Exception as exc:
        raise CrmCrudError(f"{label} does not match schema: {exc}") from exc


def _coerce_last_payload(result: dict, *, operation: str) -> dict:
    """
    Normalize the executor result into a stable, entity-focused shape for ctx.crm.<resource>.last.

    Rules (entity-only):
    - create/update/get: prefer result["object"]; fallback to {"id": result["id"]} or {}
    - delete: {"id": result["id"]} (if present)
    - list/filter: {"items": [...], "total": <int|None>, "next_cursor": <str|None>}
    """
    op = (operation or "").strip().lower()

    # Helper: safe access
    obj = result.get("object") if isinstance(result, dict) else None
    items = result.get("items") if isinstance(result, dict) else None

    if op in {"create", "update", "get"}:
        if isinstance(obj, dict):
            return obj
        if isinstance(obj, list):
            return {"items": obj}
        rid = result.get("id") if isinstance(result, dict) else None
        return {"id": rid} if rid is not None else {}

    if op == "delete":
        rid = result.get("id") if isinstance(result, dict) else None
        return {"id": rid} if rid is not None else {}

    if op in {"list", "filter"}:
        return {
            "items": items if isinstance(items, list) else [],
            "total": result.get("total") if isinstance(result, dict) else None,
            "next_cursor": result.get("next_cursor") if isinstance(result, dict) else None,
        }

    # Fallback: return the raw result (best-effort) if we don't recognize the op.
    return result if isinstance(result, dict) else {}


def _write_ctx_crm(resource_slug: str, operation: str, result: dict, ctx: dict, node: dict) -> None:
    """Persist last CRM result into ctx.crm.<resource>.last/meta."""

    try:
        from datetime import datetime, timezone
    except Exception:
        return

    if not isinstance(ctx, dict):
        return

    # Ensure top-level containers exist.
    crm_bucket = ctx.setdefault("crm", {})
    if not isinstance(crm_bucket, dict):
        return
    resource_bucket = crm_bucket.setdefault(resource_slug, {})
    if not isinstance(resource_bucket, dict):
        return

    last = _coerce_last_payload(result if isinstance(result, dict) else {}, operation=operation)
    meta = {
        "node_id": node.get("id"),
        "executor": "tool_crm_crud",
        "operation": operation,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "run_id": ctx.get("flow_execution_id") or ctx.get("execution_id") or ctx.get("run_id"),
    }

    resource_bucket["last"] = last
    resource_bucket["meta"] = meta


def execute_crm_crud(node: dict, payload: Any, ctx: dict) -> dict:
    """Executor for the consolidated CRM CRUD node."""
    config = node.get("config") or {}
    resource_slug = (config.get("resource_slug") or config.get("resource") or "").strip().lower()
    operation = (config.get("operation") or config.get("op") or "").strip().lower()
    input_template = config.get("input") or {}

    if not resource_slug:
        raise CrmCrudError("Missing resource_slug")
    if not operation:
        raise CrmCrudError("Missing operation")

    resource = get_resource(resource_slug)
    if resource is None:
        raise CrmCrudError(f"Unknown CRM resource '{resource_slug}'")
    op_contract = resource.operations.get(operation)
    if op_contract is None:
        raise CrmCrudError(f"Unsupported operation '{operation}' for resource '{resource_slug}'")

    # Resolve templates (prefer ctx.*).
    resolved_input = _render_templates(deepcopy(input_template), payload=payload, ctx=ctx)

    # Validate input against the contract schema.
    _validate_jsonschema(op_contract.input_schema, resolved_input, label="CRM CRUD input")

    # Sandbox mode: do not touch DB/external services.
    if ctx.get("$sandbox"):
        if operation in {"list", "filter"}:
            sandbox_result = {"success": True, "items": [], "total": 0}
        elif operation == "delete":
            any_id = (
                resolved_input.get("contact_id")
                or resolved_input.get("ticket_id")
                or resolved_input.get("deal_id")
                or resolved_input.get("audience_id")
                or "sandbox-id"
            )
            sandbox_result = {"success": True, "id": str(any_id)}
        else:
            sandbox_result = {"success": True, "id": "sandbox-id", "object": resolved_input}

        _write_ctx_crm(resource_slug, operation, sandbox_result, ctx, node)
        return sandbox_result

    # Delegate to handlers (implemented per resource/op).
    from flows.core.executors.crm_crud_handlers import dispatch_crm_operation

    result = dispatch_crm_operation(
        resource_slug=resource_slug,
        operation=operation,
        data=resolved_input,
        ctx=ctx,
    )

    # Validate output against output schema.
    _validate_jsonschema(op_contract.output_schema, result, label="CRM CRUD output")
    _write_ctx_crm(resource_slug, operation, result, ctx, node)
    return result


__all__ = ["CrmCrudError", "execute_crm_crud"]

