# nl_rules_normalize.py
from typing import Any, Dict, Iterable, List, Optional
from dataclasses import dataclass
from functools import lru_cache
from django.db import models
from django.db.models import Q, Model, Field

ALLOWED_OPS = {
    "eq","neq","contains","startswith","endswith","regex",
    "in","between","gt","gte","lt","lte","isnull","istrue","isfalse"
}


@dataclass(frozen=True)
class Rule:
    field: str
    op: str
    value: Any = None
    value_to: Any = None
    case: Optional[str] = None   # "ci" | "cs"
    or_group: Optional[str] = None

def _norm_dunder(path: str) -> str:
    return path.replace(".", "__")


@lru_cache(maxsize=512)
def _resolve_field(model: type[Model], path: str) -> Field:
    parts = _norm_dunder(path).split("__")
    m = model
    f: Field
    for i, p in enumerate(parts):
        f = m._meta.get_field(p)
        if i < len(parts) - 1:
            rel = getattr(f, "remote_field", None)
            if not rel:
                raise ValueError(f"Path '{path}' not relational at '{p}'")
            m = rel.model
    return f  # type: ignore


def _is_string_field(f: Field) -> bool:
    return isinstance(f, (models.CharField, models.TextField, models.EmailField, models.SlugField))


def normalize_rules_from_llm_json(
    llm_json: Dict[str, Any],
    *,
    field_allowlist: Iterable[str],
    field_synonyms: Dict[str, str],
    op_synonyms: Dict[str, str],
) -> List[Rule]:
    """
    Input: LLM JSON like {"rules":[{"field":"telefono","op":"empieza con","value":"+598"}]}
    Output: normalized canonical rules (dunder fields, canonical ops).
    Unknown fields/ops are dropped (fail-closed).
    """
    out: List[Rule] = []
    items = (llm_json or {}).get("rules", [])
    for r in items:
        raw_field = str(r.get("field", "")).strip()
        raw_op = str(r.get("op", "")).strip().lower()

        # field canonicalization
        field_key = raw_field.lower()
        field = field_synonyms.get(field_key, raw_field)
        field = _norm_dunder(field)

        # op canonicalization
        op = op_synonyms.get(raw_op, raw_op)

        # allow/ops check
        if field not in set(field_allowlist):  # strict allow
            continue
        if op not in ALLOWED_OPS:
            continue

        out.append(Rule(
            field=field,
            op=op,
            value=r.get("value"),
            value_to=r.get("value_to"),
            case=r.get("case"),
            or_group=r.get("or_group"),
        ))
    return out


def _lookup_suffix(op: str, case: str, is_string: bool) -> str:
    if op == "eq":        return "iexact" if (case == "ci" and is_string) else "exact"
    if op == "neq":       return "iexact" if (case == "ci" and is_string) else "exact"
    if op == "contains":  return "icontains" if (case == "ci" and is_string) else "contains"
    if op == "startswith":return "istartswith" if (case == "ci" and is_string) else "startswith"
    if op == "endswith":  return "iendswith" if (case == "ci" and is_string) else "endswith"
    if op == "regex":     return "iregex" if (case == "ci" and is_string) else "regex"
    return op


def rules_to_q(model: type[Model], rules: List[Rule], *, default_ci: bool = True, ci_in_threshold:int = 20) -> Q:
    # AND by default; OR for matching or_group labels
    buckets = {}
    for r in rules: buckets.setdefault(r.or_group, []).append(r)

    def rule_q(r: Rule) -> Q:
        f = _resolve_field(model, r.field)
        is_str = _is_string_field(f)
        case = (r.case or ("ci" if default_ci else "cs")).lower()

        if r.op == "neq":
            sfx = _lookup_suffix("neq", case, is_str)
            return ~Q(**{f"{r.field}__{sfx}": r.value})
        if r.op == "between":
            return Q(**{f"{r.field}__gte": r.value, f"{r.field}__lte": r.value_to})
        if r.op == "in":
            vals = list(r.value or [])
            if is_str and case == "ci" and 0 < len(vals) <= ci_in_threshold:
                q = None
                for v in vals:
                    qv = Q(**{f"{r.field}__iexact": v})
                    q = qv if q is None else (q | qv)
                return q or Q()
            return Q(**{f"{r.field}__in": vals})
        if r.op in {"gt","gte","lt","lte","isnull"}:
            return Q(**{f"{r.field}__{r.op}": r.value})
        if r.op in {"istrue","isfalse"}:
            return Q(**{r.field: (r.op == "istrue")})

        sfx = _lookup_suffix(r.op, case, is_str)
        return Q(**{f"{r.field}__{sfx}": r.value})

    final = None
    for label, items in buckets.items():
        if label is None:
            for r in items:
                q = rule_q(r); final = q if final is None else (final & q)
        else:
            or_q = None
            for r in items:
                q = rule_q(r); or_q = q if or_q is None else (or_q | q)
            final = or_q if final is None else (final & (or_q or Q()))
    return final or Q()
