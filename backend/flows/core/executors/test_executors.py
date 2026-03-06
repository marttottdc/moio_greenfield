"""
Test script for Flow Executors

Verifies that all Celery tasks return proper ExecutorResult structure
for downstream chaining.

Run with: python -m flows.core.executors.test_executors
"""

from __future__ import annotations

import json
from typing import Dict, Any, List

from .base import (
    ExecutorResult,
    ExecutorContext,
    create_result,
    create_error_result,
    resolve_expression,
    resolve_mapping,
    log_entry,
)


def validate_executor_result(result: Dict[str, Any], name: str) -> List[str]:
    """
    Validate that an executor result has the required structure.
    
    Expected structure:
    {
        "success": bool,
        "data": {...},
        "logs": [...],
        "error": str | None,
        "metadata": {...}
    }
    
    Returns:
        List of validation errors (empty if valid)
    """
    errors = []
    
    if not isinstance(result, dict):
        return [f"{name}: Result is not a dict, got {type(result).__name__}"]
    
    if "success" not in result:
        errors.append(f"{name}: Missing 'success' field")
    elif not isinstance(result["success"], bool):
        errors.append(f"{name}: 'success' should be bool, got {type(result['success']).__name__}")
    
    if "data" not in result:
        errors.append(f"{name}: Missing 'data' field")
    elif not isinstance(result["data"], dict):
        errors.append(f"{name}: 'data' should be dict, got {type(result['data']).__name__}")
    
    if "logs" not in result:
        errors.append(f"{name}: Missing 'logs' field")
    elif not isinstance(result["logs"], list):
        errors.append(f"{name}: 'logs' should be list, got {type(result['logs']).__name__}")
    else:
        for i, log in enumerate(result["logs"]):
            if not isinstance(log, dict):
                errors.append(f"{name}: logs[{i}] should be dict")
                continue
            if "timestamp" not in log:
                errors.append(f"{name}: logs[{i}] missing 'timestamp'")
            if "level" not in log:
                errors.append(f"{name}: logs[{i}] missing 'level'")
            if "message" not in log:
                errors.append(f"{name}: logs[{i}] missing 'message'")
    
    if "error" not in result:
        errors.append(f"{name}: Missing 'error' field")
    elif result["error"] is not None and not isinstance(result["error"], str):
        errors.append(f"{name}: 'error' should be str or None, got {type(result['error']).__name__}")
    
    if "metadata" not in result:
        errors.append(f"{name}: Missing 'metadata' field")
    elif not isinstance(result["metadata"], dict):
        errors.append(f"{name}: 'metadata' should be dict, got {type(result['metadata']).__name__}")
    
    return errors


def test_base_utilities():
    """Test base utility functions."""
    print("\n=== Testing Base Utilities ===")
    errors = []
    
    result = create_result(success=True, data={"key": "value"})
    validation_errors = validate_executor_result(result, "create_result")
    errors.extend(validation_errors)
    
    error_result = create_error_result("Test error", data={"debug": "info"})
    validation_errors = validate_executor_result(error_result, "create_error_result")
    errors.extend(validation_errors)
    
    if not error_result["success"] == False:
        errors.append("create_error_result: success should be False")
    if error_result["error"] != "Test error":
        errors.append("create_error_result: error message not set correctly")
    
    log = log_entry("INFO", "Test message", {"data": 123})
    if not hasattr(log, 'timestamp'):
        errors.append("log_entry: missing timestamp")
    if log.level != "INFO":
        errors.append("log_entry: level not set correctly")
    
    payload = {"name": "John", "nested": {"value": 42}}
    ctx = {"$input": {"initial": "data"}}
    
    resolved = resolve_expression("{{name}}", payload, ctx)
    if resolved != "John":
        errors.append(f"resolve_expression: expected 'John', got '{resolved}'")
    
    resolved = resolve_expression("{{nested.value}}", payload, ctx)
    if resolved != 42:
        errors.append(f"resolve_expression: expected 42, got '{resolved}'")
    
    mapping = {"output_name": "{{name}}", "output_value": "{{nested.value}}"}
    resolved_mapping = resolve_mapping(mapping, payload, ctx)
    if resolved_mapping.get("output_name") != "John":
        errors.append(f"resolve_mapping: expected 'John', got '{resolved_mapping.get('output_name')}'")
    
    if errors:
        print(f"FAILED: {len(errors)} errors")
        for e in errors:
            print(f"  - {e}")
    else:
        print("PASSED: All base utility tests passed")
    
    return errors


def test_executor_context():
    """Test ExecutorContext context manager."""
    print("\n=== Testing ExecutorContext ===")
    errors = []
    
    with ExecutorContext("test_executor", "test-task-123") as ctx:
        ctx.result.info("Test info message")
        ctx.result.warning("Test warning")
        ctx.result.data = {"test": "data"}
    
    result = ctx.result.to_dict()
    validation_errors = validate_executor_result(result, "ExecutorContext")
    errors.extend(validation_errors)
    
    if result["metadata"].get("executor") != "test_executor":
        errors.append("ExecutorContext: executor name not in metadata")
    if result["metadata"].get("task_id") != "test-task-123":
        errors.append("ExecutorContext: task_id not in metadata")
    if "started_at" not in result["metadata"]:
        errors.append("ExecutorContext: started_at not in metadata")
    if "finished_at" not in result["metadata"]:
        errors.append("ExecutorContext: finished_at not in metadata")
    if "duration_ms" not in result["metadata"]:
        errors.append("ExecutorContext: duration_ms not in metadata")
    
    if len(result["logs"]) < 2:
        errors.append("ExecutorContext: expected at least 2 log entries")
    
    if errors:
        print(f"FAILED: {len(errors)} errors")
        for e in errors:
            print(f"  - {e}")
    else:
        print("PASSED: ExecutorContext tests passed")
    
    return errors


def test_executor_result_chaining():
    """Test that executor results can be chained correctly."""
    print("\n=== Testing Result Chaining ===")
    errors = []
    
    first_result = create_result(
        success=True,
        data={"contact_id": "123", "name": "John Doe"},
    )
    
    second_payload = first_result["data"]
    
    ctx = {"previous_node": first_result["data"]}
    
    resolved = resolve_expression("{{previous_node.contact_id}}", {}, ctx)
    if resolved != "123":
        errors.append(f"Chaining: expected '123', got '{resolved}'")
    
    resolved = resolve_expression("{{contact_id}}", second_payload, ctx)
    if resolved != "123":
        errors.append(f"Chaining: expected '123' from payload, got '{resolved}'")
    
    if errors:
        print(f"FAILED: {len(errors)} errors")
        for e in errors:
            print(f"  - {e}")
    else:
        print("PASSED: Result chaining tests passed")
    
    return errors


def test_executor_registry():
    """Test that all executors are registered correctly."""
    print("\n=== Testing Executor Registry ===")
    errors = []
    
    from . import EXECUTOR_REGISTRY, get_executor, list_executors
    
    expected_executors = [
        "whatsapp_template",
        "email_template",
        "create_contact",
        "upsert_contact",
        "create_ticket",
        "update_candidate_status",
        "search_contacts",
        "http_request",
        "webhook_trigger",
        "schedule_trigger",
        "event_trigger",
        "manual_trigger",
        "store_result",
        "notify_completion",
        "webhook_response",
        "log_completion",
        "debug_log",
        "passthrough",
    ]
    
    for executor_name in expected_executors:
        if executor_name not in EXECUTOR_REGISTRY:
            errors.append(f"Registry: missing executor '{executor_name}'")
        else:
            executor = get_executor(executor_name)
            if not callable(executor):
                errors.append(f"Registry: executor '{executor_name}' is not callable")
    
    registered = list_executors()
    if set(registered) != set(expected_executors):
        missing = set(expected_executors) - set(registered)
        extra = set(registered) - set(expected_executors)
        if missing:
            errors.append(f"Registry: missing executors: {missing}")
        if extra:
            print(f"  Note: Extra executors registered: {extra}")
    
    if errors:
        print(f"FAILED: {len(errors)} errors")
        for e in errors:
            print(f"  - {e}")
    else:
        print(f"PASSED: All {len(expected_executors)} executors registered")
    
    return errors


def run_all_tests():
    """Run all tests and report results."""
    print("=" * 60)
    print("Flow Executors Test Suite")
    print("=" * 60)
    
    all_errors = []
    
    all_errors.extend(test_base_utilities())
    all_errors.extend(test_executor_context())
    all_errors.extend(test_executor_result_chaining())
    all_errors.extend(test_executor_registry())
    
    print("\n" + "=" * 60)
    if all_errors:
        print(f"TOTAL: {len(all_errors)} errors found")
        print("=" * 60)
        return 1
    else:
        print("ALL TESTS PASSED")
        print("=" * 60)
        return 0


if __name__ == "__main__":
    import sys
    sys.exit(run_all_tests())
