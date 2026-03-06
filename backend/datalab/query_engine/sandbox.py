"""
Sandbox for running user-provided code (post_process or snippets).

- Restricted __builtins__; no filesystem/network.
- Optional timeout (signal-based on main thread; best-effort).
- In-process execution so injected ctx.run_sql / run_view can use the DB.
"""
from __future__ import annotations

import ast
import signal
import logging
import inspect
from typing import Any, Callable

logger = logging.getLogger(__name__)

# Max size of code string (bytes)
MAX_CODE_SIZE = 16 * 1024

# Safe builtins (no open, exec, eval, __import__, etc.)
SAFE_BUILTINS = {
    "abs": abs,
    "all": all,
    "any": any,
    "bool": bool,
    "dict": dict,
    "enumerate": enumerate,
    "float": float,
    "int": int,
    "len": len,
    "list": list,
    "max": max,
    "min": min,
    "range": range,
    "round": round,
    "set": set,
    "sorted": sorted,
    "str": str,
    "sum": sum,
    "tuple": tuple,
    "zip": zip,
    "map": map,
    "filter": filter,
    "isinstance": isinstance,
    "None": None,
    "True": True,
    "False": False,
}


class SandboxError(Exception):
    """Raised when sandbox execution fails (timeout, size, or runtime error)."""
    pass


class _TimeoutError(SandboxError):
    """Raised when execution exceeds the timeout."""
    pass


def _validate_sandbox_ast(tree: ast.AST) -> None:
    """
    Reject dangerous Python constructs before execution.

    This is still an in-process sandbox and should not be considered fully secure,
    but it blocks the known dunder/introspection escape vectors.
    """
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            raise SandboxError("Import statements are not allowed")
        if isinstance(node, ast.Attribute) and node.attr.startswith("__"):
            raise SandboxError("Dunder attribute access is not allowed")
        if isinstance(node, ast.Name) and node.id.startswith("__"):
            raise SandboxError("Dunder names are not allowed")
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and node.name.startswith("__"):
            raise SandboxError("Dunder definitions are not allowed")


def _call_entrypoint(fn: Callable[..., Any], globals_inject: dict[str, Any]) -> Any:
    """Call run/main with compatible args for post-process and snippets."""
    if "result" in globals_inject:
        return fn(globals_inject["result"])

    if "ctx" in globals_inject:
        ctx = globals_inject["ctx"]
        try:
            sig = inspect.signature(fn)
        except (TypeError, ValueError):
            return fn(ctx)

        positional = [
            p
            for p in sig.parameters.values()
            if p.kind in (inspect.Parameter.POSITIONAL_ONLY, inspect.Parameter.POSITIONAL_OR_KEYWORD)
        ]
        has_var_positional = any(p.kind == inspect.Parameter.VAR_POSITIONAL for p in sig.parameters.values())
        if has_var_positional or len(positional) >= 1:
            return fn(ctx)
        return fn()

    return fn()


def _timeout_handler(signum: int, frame: Any) -> None:
    raise _TimeoutError("Execution exceeded time limit")


def run_sandboxed_code(
    code: str,
    globals_inject: dict[str, Any],
    timeout_seconds: int = 30,
) -> Any:
    """
    Execute user code in a restricted namespace and return the result.

    The code is expected to define a function `run` or `main`, or to set
    a variable `RESULT` or `result`. That value is returned.

    Args:
        code: Python source (must be under MAX_CODE_SIZE).
        globals_inject: Namespace additions (e.g. result, ctx, pandas).
        timeout_seconds: Best-effort timeout (signal.SIGALRM on Unix main thread).

    Returns:
        The value returned by run/main or RESULT/result.

    Raises:
        SandboxError: If code too long, timeout, or runtime error.
    """
    if len(code.encode("utf-8")) > MAX_CODE_SIZE:
        raise SandboxError(f"Code exceeds maximum size of {MAX_CODE_SIZE} bytes")

    namespace = {
        "__name__": "__main__",
        "__builtins__": SAFE_BUILTINS,
        **globals_inject,
    }

    old_handler = None
    if timeout_seconds > 0:
        try:
            old_handler = signal.signal(signal.SIGALRM, _timeout_handler)
            signal.alarm(timeout_seconds)
        except (ValueError, AttributeError):
            # SIGALRM not available (e.g. Windows) or not in main thread
            pass

    try:
        tree = ast.parse(code, filename="<datalab_sandbox>", mode="exec")
        _validate_sandbox_ast(tree)
        exec(compile(tree, "<datalab_sandbox>", "exec"), namespace, namespace)

        fn = namespace.get("run") or namespace.get("main")
        if callable(fn):
            return _call_entrypoint(fn, globals_inject)
        if "RESULT" in namespace:
            return namespace["RESULT"]
        if "result" in namespace:
            return namespace["result"]
        return None
    except _TimeoutError:
        raise
    except Exception as e:
        raise SandboxError(str(e)) from e
    finally:
        if timeout_seconds > 0 and old_handler is not None:
            try:
                signal.alarm(0)
                signal.signal(signal.SIGALRM, old_handler)
            except Exception:
                pass

