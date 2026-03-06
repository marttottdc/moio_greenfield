"""Validation utilities for flow scripts."""
from __future__ import annotations

import ast
import json
from typing import Dict, Tuple


class ScriptValidationError(Exception):
    """Raised when a script payload fails validation."""


_FORBIDDEN_NODES = (
    ast.Import,
    ast.ImportFrom,
    ast.Global,
    ast.Nonlocal,
)


def _check_ast(code: str) -> Tuple[list[str], list[str]]:
    messages: list[str] = []
    warnings: list[str] = []
    try:
        tree = ast.parse(code, filename="<script>")
    except SyntaxError as exc:  # pragma: no cover - handled by caller
        raise ScriptValidationError(
            f"Syntax error on line {exc.lineno}: {exc.msg}"
        ) from exc

    for node in ast.walk(tree):
        if isinstance(node, _FORBIDDEN_NODES):
            raise ScriptValidationError(
                "Import, global, and nonlocal statements are not allowed in scripts."
            )
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            if node.func.id == "open":
                warnings.append(
                    "Usage of open() may fail because file access is not permitted."
                )
    messages.append("Syntax looks good.")
    return messages, warnings


def validate_script_payload(
    name: str,
    description: str,
    code: str,
    params_text: str,
) -> Tuple[Dict[str, str], list[str], dict]:
    """Validate script metadata and payload, returning (errors, messages, params)."""

    errors: Dict[str, str] = {}
    messages: list[str] = []
    params: dict = {}

    if not name:
        errors["name"] = "Name is required."

    stripped_code = (code or "").strip()
    if not stripped_code:
        errors["code"] = "Script body cannot be empty."
    else:
        try:
            ast_messages, ast_warnings = _check_ast(stripped_code)
            messages.extend(ast_messages)
            messages.extend(ast_warnings)
        except ScriptValidationError as exc:
            errors["code"] = str(exc)

    if description and len(description) > 2000:
        errors["description"] = "Description is too long."

    text = (params_text or "").strip()
    if text:
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError as exc:
            errors["params"] = (
                f"Invalid JSON: {exc.msg} (line {exc.lineno}, column {exc.colno})"
            )
            parsed = {}
        else:
            if not isinstance(parsed, dict):
                errors["params"] = "Parameters JSON must be an object."
            else:
                params = parsed
                messages.append("Parameters JSON is valid.")
    else:
        params = {}
        messages.append("Parameters JSON is valid.")

    return errors, messages, params
