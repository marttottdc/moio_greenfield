from datetime import UTC, datetime
import html as _html
import re
from typing import Mapping, Any, Literal, NamedTuple

ISO_TIMESTAMP_FORMAT = "%Y-%m-%dT%H:%M:%S.%fZ"

_SAFE_BUILTINS: Mapping[str, Any] = {
    "len": len,
    "min": min,
    "max": max,
    "sum": sum,
    "any": any,
    "all": all,
    "sorted": sorted,
    "str": str,
    "int": int,
    "float": float,
    "bool": bool,
    "enumerate": enumerate,
    "range": range,
    "list": list,
    "dict": dict,
    "set": set,
    # Safe helper for HTML email templates.
    "escape": _html.escape,
}

_CONTRACT_PATH_RE = re.compile(r"^[A-Za-z0-9_-]+(\.[A-Za-z0-9_-]+)*$")


class DotAccessDict(dict):
    """Dictionary that supports both bracket and dot notation access.
    
    Allows expressions like:
    - obj.key instead of obj['key']
    - obj.nested.field instead of obj['nested']['field']
    - ctx.Webhook.template_id instead of ctx['Webhook']['template_id']
    
    Works recursively - nested dicts are also wrapped.
    """
    
    def __getattr__(self, key: str) -> Any:
        try:
            value = self[key]
            # Recursively wrap dicts for nested dot access
            if isinstance(value, dict) and not isinstance(value, DotAccessDict):
                return DotAccessDict(value)
            return value
        except KeyError:
            # For flow expressions, missing keys should resolve to None (not raise),
            # so Branch/Condition/While can safely check optional ctx paths.
            return None
    
    def __setattr__(self, key: str, value: Any) -> None:
        self[key] = value
    
    def __delattr__(self, key: str) -> None:
        try:
            del self[key]
        except KeyError:
            raise AttributeError(f"'{type(self).__name__}' object has no attribute '{key}'")


def _now_iso() -> str:
    return datetime.now(UTC).strftime(ISO_TIMESTAMP_FORMAT)


class _ParsedContractPath(NamedTuple):
    namespace: Literal["input", "nodes", "config", "ctx"]
    node_id: str | None
    parts: list[str]


def _parse_contract_path(expr: str) -> _ParsedContractPath:
    """Parse and validate a contract path.

    Allowed forms:
    - input.body.<field>(.<field>)*
    - nodes.<nodeId>.output.<field>(.<field>)*
    - config.<field>(.<field>)*
    - ctx.<field>(.<field>)*

    No other namespaces or expression syntax are allowed.
    """
    expr = _normalize_placeholder_expr(expr)
    if not expr or not _CONTRACT_PATH_RE.match(expr):
        raise ValueError(
            f"Invalid placeholder '{expr}'. Only simple dot-paths are allowed."
        )
    parts = [p for p in expr.split(".") if p]
    if len(parts) >= 2 and parts[0] == "input" and parts[1] == "body":
        return _ParsedContractPath("input", None, parts[2:])
    if len(parts) >= 3 and parts[0] == "nodes" and parts[2] == "output":
        return _ParsedContractPath("nodes", parts[1], parts[3:])
    if len(parts) >= 2 and parts[0] == "config":
        return _ParsedContractPath("config", None, parts[1:])
    if len(parts) >= 2 and parts[0] == "ctx":
        return _ParsedContractPath("ctx", None, parts[1:])
    raise ValueError(
        f"Invalid placeholder '{expr}'. Allowed namespaces are "
        "'input.body.*', 'nodes.<nodeId>.output.*', 'config.*', and 'ctx.*'."
    )


_CTX_HIDDEN_KEYS = {
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


def _ctx_view(context: dict) -> dict:
    """Return the internal-contract view of the runtime context for `ctx.*`.

    `ctx` is the stable internal contract produced by Normalize. It intentionally
    hides runtime/system keys such as $input, config, nodes, etc.
    """
    if not isinstance(context, dict):
        return {}
    view = {
        k: v
        for k, v in context.items()
        if isinstance(k, str)
        and not k.startswith("$")
        and k not in _CTX_HIDDEN_KEYS
    }
    # Expose read-only aliases for last results (currently CRM).
    crm_data = context.get("crm") if isinstance(context.get("crm"), dict) else {}
    if isinstance(crm_data, dict):
        view.setdefault("crm", crm_data)
        view.setdefault("last", {"crm": {}})
        for res, bucket in crm_data.items():
            if not isinstance(bucket, dict):
                continue
            view["last"]["crm"][res] = bucket.get("last")
    return view


def resolve_contract_path(expr: str, context: dict) -> Any:
    """Resolve an allowed contract path against the flow runtime context."""
    parsed = _parse_contract_path(expr)

    if parsed.namespace == "input":
        container = context.get("$input") or {}
        if not isinstance(container, dict):
            raise KeyError("Missing '$input' in runtime context")
        base = container.get("body") or {}
        if not isinstance(base, dict):
            raise KeyError("Invalid '$input.body' in runtime context (expected object)")
        current: Any = base
    elif parsed.namespace == "nodes":
        nodes = context.get("nodes") or {}
        if not isinstance(nodes, dict):
            raise KeyError("Missing 'nodes' in runtime context")
        node_id = parsed.node_id or ""
        if node_id not in nodes:
            available = ", ".join(sorted(map(str, nodes.keys())))
            raise KeyError(f"Missing node '{node_id}' (available: {available})")
        node_obj = nodes.get(node_id) or {}
        if not isinstance(node_obj, dict) or "output" not in node_obj:
            raise KeyError(f"Missing output for node '{node_id}'")
        current = node_obj.get("output")
    elif parsed.namespace == "config":
        base = context.get("config")
        if base is None:
            raise KeyError("Missing 'config' in runtime context")
        if not isinstance(base, dict):
            raise KeyError("Invalid 'config' in runtime context (expected object)")
        current = base
    else:
        current = _ctx_view(context)

    for part in parsed.parts:
        if isinstance(current, dict):
            if part not in current:
                available = ", ".join(sorted(map(str, current.keys())))
                raise KeyError(f"Missing key '{part}' (available: {available})")
            current = current.get(part)
        else:
            # Contract paths do not support attribute access or list indexing.
            raise KeyError(
                f"Cannot resolve '{part}' on non-object value ({type(current).__name__})"
            )
    return current


def _resolve_template(value: Any, payload: Any, context: dict) -> Any:
    """Resolve a single {{path}} expression (paths only)."""
    if not isinstance(value, str):
        return value
    raw = value.strip()
    if raw.startswith("{{") and raw.endswith("}}"):
        raw = raw[2:-2].strip()
    return resolve_contract_path(raw, context)


_TEMPLATE_RE = re.compile(r"\{\{\s*(.*?)\s*\}\}")


def _normalize_placeholder_expr(expr: str) -> str:
    """Normalize common WYSIWYG artifacts inside {{ ... }}."""
    expr = (expr or "").strip()
    # Some editors can introduce an extra '{' token: {{ { input.body.foo }}
    if expr.startswith("{"):
        expr = expr[1:].strip()
    if expr.endswith("}"):
        expr = expr[:-1].strip()
    return expr


def render_template_string(
    value: Any,
    payload: Any,
    context: dict,
    *,
    autoescape_html: bool = False,
) -> Any:
    """
    Render a string containing one or more {{path}} placeholders.

    Strict flow language contract:
    - Only `input.body.*`, `nodes.<nodeId>.output.*`, `config.*`, and `ctx.*` are addressable.
    - Placeholders must be simple dot-paths (no operators, calls, indexing, etc).

    If the input is not a string, it is returned as-is.
    """
    if not isinstance(value, str):
        return value
    if "{{" not in value or "}}" not in value:
        return value

    def repl(match: re.Match) -> str:
        expr = match.group(1)
        try:
            rendered = resolve_contract_path(expr, context)
        except Exception as e:
            raise ValueError(f"Failed to render '{{{{ {expr.strip()} }}}}': {e}") from e
        if rendered is None:
            return ""

        # Autoescape only placeholder output (not the surrounding template HTML).
        # This makes HTML email templates safe-by-default.
        if autoescape_html:
            return _html.escape(str(rendered))

        return str(rendered)

    return _TEMPLATE_RE.sub(repl, value)
