"""Formula evaluation for flow configuration fields.

This module provides a small, safe expression language intended for *data*
transformations (unlike `flows.core.expressions`, which is for control-flow and
is intentionally much more restrictive).

Contract:
- Formulas are opt-in: a string starting with '=' is treated as a formula.
- Escaping: strings starting with '==' are treated as literal strings beginning with '='.
- Formulas may only reference the strict flow contract namespaces:
  - input.body.*
  - ctx.*
  - nodes.<id>.output.*
  - config.*
- No `payload.*` is exposed.
- No imports, attribute calls, indexing, comprehensions, or dunder/private access.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass
from typing import Any, Callable, Dict, Optional

from .lib import DotAccessDict, _ctx_view, resolve_contract_path


class FlowFormulaError(ValueError):
    """Raised when a formula is invalid or cannot be evaluated safely."""


@dataclass(frozen=True)
class FormulaValidationResult:
    referenced_roots: tuple[str, ...]


_ALLOWED_ROOTS = {"input", "ctx", "nodes", "config"}

# Keep the syntax intentionally small and predictable.
_ALLOWED_BIN_OPS = (ast.Add, ast.Sub, ast.Mult, ast.Div, ast.Mod)
_ALLOWED_BOOL_OPS = (ast.And, ast.Or)
_ALLOWED_UNARY_OPS = (ast.Not, ast.USub, ast.UAdd)
_ALLOWED_COMPARE_OPS = (
    ast.Eq,
    ast.NotEq,
    ast.Lt,
    ast.LtE,
    ast.Gt,
    ast.GtE,
    ast.In,
    ast.NotIn,
    ast.Is,
    ast.IsNot,
)


def _attribute_chain(node: ast.AST) -> Optional[list[str]]:
    parts: list[str] = []
    cur: ast.AST = node
    while isinstance(cur, ast.Attribute):
        parts.append(cur.attr)
        cur = cur.value
    if isinstance(cur, ast.Name):
        parts.append(cur.id)
    else:
        return None
    return list(reversed(parts))


def _reject_private_attr(attr: str) -> None:
    if not attr or attr.startswith("_"):
        raise FlowFormulaError("Private/dunder attribute access is not allowed in formulas")


class _FormulaValidator(ast.NodeVisitor):
    def __init__(self, *, allowed_functions: set[str]) -> None:
        self._allowed_functions = allowed_functions
        self._roots: set[str] = set()

    @property
    def referenced_roots(self) -> tuple[str, ...]:
        return tuple(sorted(self._roots))

    def generic_visit(self, node: ast.AST) -> Any:  # noqa: ANN401
        raise FlowFormulaError(f"Unsupported syntax in formula: {node.__class__.__name__}")

    def visit_Expression(self, node: ast.Expression) -> Any:  # noqa: ANN401
        return self.visit(node.body)

    def visit_Constant(self, node: ast.Constant) -> Any:  # noqa: ANN401
        # Allow scalar literals only.
        if isinstance(node.value, (str, int, float, bool)) or node.value is None:
            return None
        raise FlowFormulaError("Only scalar literals are allowed in formulas")

    def visit_Name(self, node: ast.Name) -> Any:  # noqa: ANN401
        if node.id in {"True", "False", "None"}:
            return None
        if node.id in _ALLOWED_ROOTS:
            self._roots.add(node.id)
            return None
        if node.id in self._allowed_functions:
            return None
        raise FlowFormulaError(f"Unknown name '{node.id}' in formula")

    def visit_Attribute(self, node: ast.Attribute) -> Any:  # noqa: ANN401
        chain = _attribute_chain(node)
        if not chain:
            raise FlowFormulaError("Invalid attribute chain in formula")
        root = chain[0]
        if root not in _ALLOWED_ROOTS:
            raise FlowFormulaError("Formulas may only reference input/ctx/nodes/config")
        self._roots.add(root)
        for part in chain[1:]:
            _reject_private_attr(part)
        # Enforce strict contract shape for `input`: must start with `input.body`
        if root == "input":
            if len(chain) == 1:
                return None
            if chain[1] != "body":
                raise FlowFormulaError("Only 'input.body.*' is allowed (not 'input.<x>')")
        return None

    def visit_Call(self, node: ast.Call) -> Any:  # noqa: ANN401
        # Only allow direct calls to approved functions: fn(...)
        if not isinstance(node.func, ast.Name):
            raise FlowFormulaError("Only direct function calls are allowed in formulas")
        fn_name = node.func.id
        if fn_name not in self._allowed_functions:
            raise FlowFormulaError(f"Function '{fn_name}' is not allowed in formulas")
        for arg in node.args:
            if isinstance(arg, ast.Starred):
                raise FlowFormulaError("Star-args are not allowed in formulas")
            self.visit(arg)
        for kw in node.keywords:
            if kw.arg is None:
                raise FlowFormulaError("**kwargs are not allowed in formulas")
            _reject_private_attr(kw.arg)
            self.visit(kw.value)
        return None

    def visit_BinOp(self, node: ast.BinOp) -> Any:  # noqa: ANN401
        if not isinstance(node.op, _ALLOWED_BIN_OPS):
            raise FlowFormulaError("Unsupported arithmetic operator in formula")
        self.visit(node.left)
        self.visit(node.right)
        return None

    def visit_UnaryOp(self, node: ast.UnaryOp) -> Any:  # noqa: ANN401
        if not isinstance(node.op, _ALLOWED_UNARY_OPS):
            raise FlowFormulaError("Unsupported unary operator in formula")
        self.visit(node.operand)
        return None

    def visit_BoolOp(self, node: ast.BoolOp) -> Any:  # noqa: ANN401
        if not isinstance(node.op, _ALLOWED_BOOL_OPS):
            raise FlowFormulaError("Unsupported boolean operator in formula")
        for v in node.values:
            self.visit(v)
        return None

    def visit_Compare(self, node: ast.Compare) -> Any:  # noqa: ANN401
        self.visit(node.left)
        for op in node.ops:
            if not isinstance(op, _ALLOWED_COMPARE_OPS):
                raise FlowFormulaError("Unsupported comparison operator in formula")
        for comp in node.comparators:
            self.visit(comp)
        return None

    def visit_Subscript(self, node: ast.Subscript) -> Any:  # noqa: ANN401
        raise FlowFormulaError("Indexing is not allowed in formulas (use dot paths or path('...'))")

    def visit_List(self, node: ast.List) -> Any:  # noqa: ANN401
        raise FlowFormulaError("List literals are not allowed in formulas")

    def visit_Dict(self, node: ast.Dict) -> Any:  # noqa: ANN401
        raise FlowFormulaError("Dict literals are not allowed in formulas")

    def visit_Set(self, node: ast.Set) -> Any:  # noqa: ANN401
        raise FlowFormulaError("Set literals are not allowed in formulas")

    def visit_ListComp(self, node: ast.ListComp) -> Any:  # noqa: ANN401
        raise FlowFormulaError("Comprehensions are not allowed in formulas")

    def visit_DictComp(self, node: ast.DictComp) -> Any:  # noqa: ANN401
        raise FlowFormulaError("Comprehensions are not allowed in formulas")

    def visit_SetComp(self, node: ast.SetComp) -> Any:  # noqa: ANN401
        raise FlowFormulaError("Comprehensions are not allowed in formulas")

    def visit_GeneratorExp(self, node: ast.GeneratorExp) -> Any:  # noqa: ANN401
        raise FlowFormulaError("Comprehensions are not allowed in formulas")

    def visit_Lambda(self, node: ast.Lambda) -> Any:  # noqa: ANN401
        raise FlowFormulaError("Lambda is not allowed in formulas")


def build_standard_formula_functions() -> Dict[str, Callable[..., Any]]:
    """Return the standard function toolset exposed to formulas."""
    from datetime import datetime, timedelta
    from django.utils.timezone import now as django_now

    def concat(*args):
        return "".join(str(a) for a in args if a is not None)

    def upper(s):
        return str(s).upper() if s else ""

    def lower(s):
        return str(s).lower() if s else ""

    def trim(s):
        return str(s).strip() if s else ""

    def replace(s, old, new):
        return str(s).replace(old, new) if s else ""

    def substring(s, start, end=None):
        s = str(s) if s else ""
        return s[start:end] if end else s[start:]

    def length(s):
        return len(s) if s else 0

    def split(s, sep=" "):
        return str(s).split(sep) if s else []

    def _round(n, decimals=0):
        try:
            return round(float(n), int(decimals))
        except (ValueError, TypeError):
            return n

    def floor(n):
        import math

        try:
            return math.floor(float(n))
        except (ValueError, TypeError):
            return n

    def ceil(n):
        import math

        try:
            return math.ceil(float(n))
        except (ValueError, TypeError):
            return n

    def _abs(n):
        try:
            return abs(float(n))
        except (ValueError, TypeError):
            return n

    def _min(*args):
        nums = [float(a) for a in args if a is not None]
        return min(nums) if nums else None

    def _max(*args):
        nums = [float(a) for a in args if a is not None]
        return max(nums) if nums else None

    def _sum(*args):
        nums = [float(a) for a in args if a is not None]
        return sum(nums)

    def now():
        return django_now().isoformat()

    def today():
        return django_now().date().isoformat()

    def date_add(date_str, amount, unit="days"):
        try:
            if isinstance(date_str, str):
                dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
            else:
                dt = date_str
            amount = int(amount)
            if unit == "days":
                result = dt + timedelta(days=amount)
            elif unit == "hours":
                result = dt + timedelta(hours=amount)
            elif unit == "minutes":
                result = dt + timedelta(minutes=amount)
            elif unit == "seconds":
                result = dt + timedelta(seconds=amount)
            elif unit == "weeks":
                result = dt + timedelta(weeks=amount)
            else:
                result = dt + timedelta(days=amount)
            return result.isoformat()
        except Exception:
            return date_str

    def date_diff(date1, date2, unit="days"):
        try:
            if isinstance(date1, str):
                dt1 = datetime.fromisoformat(date1.replace("Z", "+00:00"))
            else:
                dt1 = date1
            if isinstance(date2, str):
                dt2 = datetime.fromisoformat(date2.replace("Z", "+00:00"))
            else:
                dt2 = date2
            diff = dt1 - dt2
            if unit == "days":
                return diff.days
            if unit == "hours":
                return diff.total_seconds() / 3600
            if unit == "minutes":
                return diff.total_seconds() / 60
            if unit == "seconds":
                return diff.total_seconds()
            return diff.days
        except Exception:
            return 0

    def format_date(date_str, fmt="%Y-%m-%d"):
        try:
            if isinstance(date_str, str):
                dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
            else:
                dt = date_str
            return dt.strftime(fmt)
        except Exception:
            return date_str

    def parse_date(s, fmt="%Y-%m-%d"):
        try:
            return datetime.strptime(s, fmt).isoformat()
        except Exception:
            return s

    def if_else(condition, true_val, false_val):
        return true_val if condition else false_val

    def coalesce(*args):
        for a in args:
            if a is not None and a != "":
                return a
        return None

    def is_null(val):
        return val is None

    def is_empty(val):
        if val is None:
            return True
        if isinstance(val, str) and val.strip() == "":
            return True
        if isinstance(val, (list, dict)) and len(val) == 0:
            return True
        return False

    return {
        "concat": concat,
        "upper": upper,
        "lower": lower,
        "trim": trim,
        "replace": replace,
        "substring": substring,
        "length": length,
        "split": split,
        "round": _round,
        "floor": floor,
        "ceil": ceil,
        "abs": _abs,
        "min": _min,
        "max": _max,
        "sum": _sum,
        "now": now,
        "today": today,
        "date_add": date_add,
        "date_diff": date_diff,
        "format_date": format_date,
        "parse_date": parse_date,
        "if_else": if_else,
        "coalesce": coalesce,
        "is_null": is_null,
        "is_empty": is_empty,
    }


def build_formula_scope(*, context: dict) -> dict:
    """Build the evaluation scope for strict-contract formulas."""
    standard = build_standard_formula_functions()

    input_value = context.get("$input") if isinstance(context, dict) else None
    nodes_value = context.get("nodes") if isinstance(context, dict) else None
    config_value = context.get("config") if isinstance(context, dict) else None

    def path(expr: Any, default: Any = None) -> Any:
        """Resolve a strict contract path like 'input.body.x' or 'ctx.event.y'."""
        if expr in (None, ""):
            return default
        try:
            return resolve_contract_path(str(expr), context)
        except Exception:
            return default

    scope = {
        # Strict contract roots
        "input": DotAccessDict(input_value) if isinstance(input_value, dict) else (input_value or {}),
        "ctx": DotAccessDict(_ctx_view(context)) if isinstance(context, dict) else (context or {}),
        "nodes": DotAccessDict(nodes_value) if isinstance(nodes_value, dict) else (nodes_value or {}),
        "config": DotAccessDict(config_value) if isinstance(config_value, dict) else (config_value or {}),
        # Utility to access paths that aren't valid identifiers (or just for convenience)
        "path": path,
        # Scalar constants
        "True": True,
        "False": False,
        "None": None,
        # Basic casts
        "int": int,
        "float": float,
        "str": str,
        "len": len,
        "bool": bool,
    }
    scope.update(standard)
    return scope


def validate_formula_expression(expr: str, *, allowed_functions: set[str]) -> FormulaValidationResult:
    raw = (expr or "").strip()
    if raw == "":
        raise FlowFormulaError("Formula expression is empty")
    try:
        parsed = ast.parse(raw, mode="eval")
    except SyntaxError as exc:
        raise FlowFormulaError(f"Invalid formula syntax: {exc.msg}") from exc
    validator = _FormulaValidator(allowed_functions=allowed_functions)
    validator.visit(parsed)
    return FormulaValidationResult(referenced_roots=validator.referenced_roots)


def eval_formula_expression(expr: str, *, context: dict) -> Any:
    scope = build_formula_scope(context=context)
    allowed_functions = {k for k, v in scope.items() if callable(v)}
    validate_formula_expression(expr, allowed_functions=allowed_functions)
    try:
        return eval(expr, {"__builtins__": {}}, scope)  # noqa: S307
    except Exception as exc:  # pragma: no cover - surfaced to caller
        raise FlowFormulaError(str(exc) or exc.__class__.__name__) from exc


def maybe_eval_formula_string(value: Any, *, context: dict) -> Any:
    """Evaluate a value if it is a formula string.

    - '==foo' -> literal '=foo'
    - '=expr' -> evaluate 'expr'
    - other   -> returned unchanged
    """
    if not isinstance(value, str):
        return value
    raw = value.strip()
    if not raw.startswith("="):
        return value
    if raw.startswith("=="):
        # Escaped literal '=' prefix
        return raw[1:]
    expr = raw[1:].strip()
    return eval_formula_expression(expr, context=context)


def deep_eval_formulas(obj: Any, *, context: dict) -> Any:
    """Recursively evaluate any '=...' strings inside obj."""
    if isinstance(obj, str):
        return maybe_eval_formula_string(obj, context=context)
    if isinstance(obj, list):
        return [deep_eval_formulas(item, context=context) for item in obj]
    if isinstance(obj, tuple):
        return tuple(deep_eval_formulas(item, context=context) for item in obj)
    if isinstance(obj, dict):
        return {k: deep_eval_formulas(v, context=context) for k, v in obj.items()}
    return obj


__all__ = [
    "FlowFormulaError",
    "FormulaValidationResult",
    "build_formula_scope",
    "build_standard_formula_functions",
    "deep_eval_formulas",
    "eval_formula_expression",
    "maybe_eval_formula_string",
    "validate_formula_expression",
]

