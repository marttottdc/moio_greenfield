"""Sandboxed expression evaluation for flow control nodes.

This module defines a narrow, declarative expression language intended for
control-flow nodes such as Branch/Condition/While and (future) FSM guards.

Contract:
- Expressions are *not* Python scripting.
- Only boolean logic + comparisons are allowed.
- Only `ctx.*` reads are allowed (no payload, no input, no globals).
- No function calls, no indexing, no attribute access outside `ctx.*`.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass
from typing import Any, Optional

from .lib import DotAccessDict


class FlowExpressionError(ValueError):
    """Raised when an expression violates the sandbox contract."""


@dataclass(frozen=True)
class ExpressionValidationResult:
    referenced_ctx_paths: tuple[str, ...]


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

_ALLOWED_BOOL_OPS = (ast.And, ast.Or)
_ALLOWED_UNARY_OPS = (ast.Not,)

_RESERVED_CTX_ROOTS = {
    "config",
    "nodes",
    "$input",
    "$trigger",
    "$outputs",
    "$loops",
    "$sandbox",
    "tenant_id",
    "execution_id",
    "flow_execution_id",
}


def _attribute_chain(node: ast.AST) -> Optional[list[str]]:
    """Return attribute chain for `ctx.a.b.c` as ['ctx','a','b','c'] else None."""
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


def _ctx_path_from_attribute(node: ast.AST) -> Optional[str]:
    chain = _attribute_chain(node)
    if not chain or chain[0] != "ctx":
        return None
    # Disallow private / dunder access
    for part in chain[1:]:
        if not part or part.startswith("_"):
            raise FlowExpressionError("ctx paths must not access private attributes")
    if len(chain) >= 2:
        root = chain[1]
        if root.startswith("$") or root in _RESERVED_CTX_ROOTS:
            raise FlowExpressionError(f"ctx root '{root}' is not allowed in expressions")
    if len(chain) == 1:
        return "ctx"
    return "ctx." + ".".join(chain[1:])


class _ExpressionValidator(ast.NodeVisitor):
    def __init__(self) -> None:
        self._referenced_paths: set[str] = set()

    @property
    def referenced_ctx_paths(self) -> tuple[str, ...]:
        return tuple(sorted(self._referenced_paths))

    def generic_visit(self, node: ast.AST) -> Any:  # noqa: ANN401
        # Default deny: only allow nodes we explicitly visit.
        raise FlowExpressionError(f"Unsupported syntax: {node.__class__.__name__}")

    def visit_Expression(self, node: ast.Expression) -> Any:  # noqa: ANN401
        return self.visit(node.body)

    def visit_Constant(self, node: ast.Constant) -> Any:  # noqa: ANN401
        # Allow scalar literals only.
        if isinstance(node.value, (str, int, float, bool)) or node.value is None:
            return None
        raise FlowExpressionError("Only scalar literals are allowed in expressions")

    def visit_Name(self, node: ast.Name) -> Any:  # noqa: ANN401
        # Only allow 'ctx' as a root symbol.
        if node.id != "ctx":
            raise FlowExpressionError("Only 'ctx.*' is allowed in sandboxed expressions")
        return None

    def visit_Attribute(self, node: ast.Attribute) -> Any:  # noqa: ANN401
        # Only allow ctx.<attr>(.<attr>)* (no other object attribute access).
        path = _ctx_path_from_attribute(node)
        if path is None:
            raise FlowExpressionError("Only 'ctx.*' attribute reads are allowed")
        self._referenced_paths.add(path)
        return None

    def visit_UnaryOp(self, node: ast.UnaryOp) -> Any:  # noqa: ANN401
        if not isinstance(node.op, _ALLOWED_UNARY_OPS):
            raise FlowExpressionError("Only 'not' unary operator is allowed")
        return self.visit(node.operand)

    def visit_BoolOp(self, node: ast.BoolOp) -> Any:  # noqa: ANN401
        if not isinstance(node.op, _ALLOWED_BOOL_OPS):
            raise FlowExpressionError("Only 'and'/'or' boolean operators are allowed")
        for value in node.values:
            self.visit(value)
        return None

    def visit_Compare(self, node: ast.Compare) -> Any:  # noqa: ANN401
        self.visit(node.left)
        for op in node.ops:
            if not isinstance(op, _ALLOWED_COMPARE_OPS):
                raise FlowExpressionError("Unsupported comparison operator in expression")
        for comparator in node.comparators:
            self.visit(comparator)
        return None

    def visit_BinOp(self, node: ast.BinOp) -> Any:  # noqa: ANN401
        raise FlowExpressionError("Arithmetic is not allowed in sandboxed expressions")

    def visit_Call(self, node: ast.Call) -> Any:  # noqa: ANN401
        raise FlowExpressionError("Function calls are not allowed in sandboxed expressions")

    def visit_Subscript(self, node: ast.Subscript) -> Any:  # noqa: ANN401
        raise FlowExpressionError("Indexing is not allowed (use ctx.dot.paths)")

    def visit_List(self, node: ast.List) -> Any:  # noqa: ANN401
        raise FlowExpressionError("Lists are not allowed in sandboxed expressions")

    def visit_Dict(self, node: ast.Dict) -> Any:  # noqa: ANN401
        raise FlowExpressionError("Dict literals are not allowed in sandboxed expressions")

    def visit_Set(self, node: ast.Set) -> Any:  # noqa: ANN401
        raise FlowExpressionError("Set literals are not allowed in sandboxed expressions")

    def visit_IfExp(self, node: ast.IfExp) -> Any:  # noqa: ANN401
        raise FlowExpressionError("Conditional expressions are not allowed in sandboxed expressions")

    def visit_Lambda(self, node: ast.Lambda) -> Any:  # noqa: ANN401
        raise FlowExpressionError("Lambda is not allowed in sandboxed expressions")

    def visit_Comprehension(self, node: ast.comprehension) -> Any:  # noqa: ANN401
        raise FlowExpressionError("Comprehensions are not allowed in sandboxed expressions")


def validate_sandboxed_expression(expr: str) -> ExpressionValidationResult:
    """Validate *expr* against the sandbox contract and return referenced ctx paths."""
    if expr is None:
        raise FlowExpressionError("Expression is required")
    if not isinstance(expr, str):
        raise FlowExpressionError("Expression must be a string")
    raw = expr.strip()
    if raw == "":
        return ExpressionValidationResult(referenced_ctx_paths=())

    try:
        parsed = ast.parse(raw, mode="eval")
    except SyntaxError as exc:
        raise FlowExpressionError(f"Invalid expression syntax: {exc.msg}") from exc

    validator = _ExpressionValidator()
    validator.visit(parsed)
    return ExpressionValidationResult(referenced_ctx_paths=validator.referenced_ctx_paths)


def eval_sandboxed_expression(expr: str, *, ctx: dict) -> Any:
    """Evaluate a validated expression against *ctx* only."""
    # Validate first for consistent errors (and to avoid accidentally evaluating
    # unsupported constructs).
    validate_sandboxed_expression(expr)
    scope = {"ctx": DotAccessDict(ctx) if isinstance(ctx, dict) else ctx}
    try:
        return eval(expr, {"__builtins__": {}}, scope)  # noqa: S307
    except Exception as exc:
        raise FlowExpressionError(str(exc) or exc.__class__.__name__) from exc


__all__ = [
    "FlowExpressionError",
    "ExpressionValidationResult",
    "validate_sandboxed_expression",
    "eval_sandboxed_expression",
]

