# utils/audience_filters.py
from __future__ import annotations
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Dict, Iterable, List, Mapping, Optional, Tuple

from django.db.models import Q, Model, QuerySet
from django.utils.timezone import make_aware, get_current_timezone


# --- Configuration -----------------------------------------------------------

# Map UI field keys -> Django ORM paths (adjust to your model)
# Example for a Contact model:
FIELD_MAP: Dict[str, str] = {
    "fullname": "fullname",
    "email": "email",
    "created": "created",
    "phone": "phone",
    "whatsapp_name": "whatsapp_name",
    "company": "company",
    "source": "source",
    "ctype__name": "type",
}

# Supported operators from your ConditionForm (adjust the keys to your form)
OP_TO_LOOKUP: Mapping[str, str] = {
    "eq": "=",                 # equals
    "neq": "!=",                # not equals (we negate the Q)
    "contains": "icontains",
    "startswith": "istartswith",
    "endswith": "iendswith",
    "gt": "gt",
    "gte": "gte",
    "lt": "lt",
    "lte": "lte",
    "in": "in",               # comma-separated or list
    "between": "range",       # uses value, value_to
    "isnull": "isnull",       # value coerced to bool
    "istrue": "",             # boolean True
    "isfalse": "",            # boolean False
}


# --- Helpers ----------------------------------------------------------------

def _coerce_value(model: type[Model], orm_path: str, raw: Any) -> Any:
    """
    Coerce raw string(s) to the right Python type based on model field.
    Works for basic scalar fields. For relations or 'in', lists are preserved.
    """
    if isinstance(raw, (list, tuple)):
        return [_coerce_value(model, orm_path, v) for v in raw]

    # Allow comma-separated lists (only for 'in')
    if isinstance(raw, str) and "," in raw:
        # The caller decides when to pass lists vs scalars;
        # we keep strings intact unless 'in' uses this.
        pass

    # Find the concrete field type (follow __ path up to the last field)
    field = None
    model_ref = model
    parts = orm_path.split("__")
    try:
        for i, part in enumerate(parts):
            f = model_ref._meta.get_field(part)
            field = f
            if hasattr(f, "remote_field") and f.remote_field and i < len(parts) - 1:
                model_ref = f.remote_field.model  # follow relations
    except Exception:
        field = None  # fallback to best-effort parsing

    if field is None:
        # Best-effort: try numeric/bool/datetime
        return _best_effort(raw)

    internal = field.get_internal_type()

    if internal in {"BooleanField", "NullBooleanField"}:
        return _to_bool(raw)

    if internal in {"IntegerField", "BigIntegerField", "SmallIntegerField",
                    "PositiveIntegerField", "PositiveSmallIntegerField", "AutoField"}:
        return int(raw) if raw != "" and raw is not None else None

    if internal in {"FloatField"}:
        return float(raw) if raw != "" and raw is not None else None

    if internal in {"DecimalField"}:
        return Decimal(str(raw)) if raw != "" and raw is not None else None

    if internal in {"DateField"}:
        if isinstance(raw, date) and not isinstance(raw, datetime):
            return raw
        if isinstance(raw, datetime):
            return raw.date()
        if raw in (None, ""):
            return None
        # ISO: YYYY-MM-DD
        return date.fromisoformat(str(raw))

    if internal in {"DateTimeField"}:
        if isinstance(raw, datetime):
            return raw if raw.tzinfo else make_aware(raw, get_current_timezone())
        if raw in (None, ""):
            return None
        # ISO: 2025-08-12T10:30:00 or "2025-08-12 10:30:00"
        val = datetime.fromisoformat(str(raw).replace(" ", "T"))
        return val if val.tzinfo else make_aware(val, get_current_timezone())

    # Char/Text and everything else
    return raw


def _best_effort(raw: Any) -> Any:
    s = str(raw).strip() if isinstance(raw, str) else raw
    if s in (None, ""):
        return None
    # bool
    if isinstance(s, str) and s.lower() in {"true", "false", "1", "0", "yes", "no"}:
        return _to_bool(s)
    # int
    try:
        return int(s)
    except Exception:
        pass
    # float/decimal
    try:
        return Decimal(str(s))
    except Exception:
        pass
    # datetime iso
    try:
        val = datetime.fromisoformat(str(s).replace(" ", "T"))
        return val if val.tzinfo else make_aware(val, get_current_timezone())
    except Exception:
        pass
    # date iso
    try:
        return date.fromisoformat(str(s))
    except Exception:
        pass
    return raw


def _to_bool(v: Any) -> bool:
    if isinstance(v, bool):
        return v
    if v is None:
        return False
    vs = str(v).strip().lower()
    return vs in {"true", "1", "yes", "y", "on"}


def _split_if_csv(value: Any) -> List[str]:
    if isinstance(value, str) and "," in value:
        return [x.strip() for x in value.split(",") if x.strip() != ""]
    return [value]


def _rule_to_q(model: type[Model], rule: Dict[str, Any], field_map: Mapping[str, str]) -> Optional[Q]:
    """
    Convert one cleaned_data rule into a Q() object.
    Expected rule keys (adapt if your form differs):
      - field: UI key (mapped via field_map)
      - op: one of OP_TO_LOOKUP keys
      - value: scalar or list
      - value_to: for 'between'
      - negate: optional bool
    """
    if not rule or rule.get("DELETE"):
        return None

    ui_field = rule.get("field")
    op_key = (rule.get("op") or "eq").lower()
    if not ui_field or op_key not in OP_TO_LOOKUP:
        return None

    orm_path = field_map.get(ui_field, ui_field)
    lookup = OP_TO_LOOKUP[op_key]

    # Prepare values
    if op_key in {"istrue", "isfalse"}:
        py_val = True if op_key == "istrue" else False
        q = Q(**{orm_path: py_val})

    elif op_key == "between":
        v1 = _coerce_value(model, orm_path, rule.get("value"))
        v2 = _coerce_value(model, orm_path, rule.get("value_to"))
        if v1 is None or v2 is None:
            return None
        q = Q(**{f"{orm_path}__range": (v1, v2)})

    elif op_key == "in":
        raw = rule.get("value")
        items = raw if isinstance(raw, (list, tuple)) else _split_if_csv(raw)
        coerced = [_coerce_value(model, orm_path, x) for x in items]
        q = Q(**{f"{orm_path}__in": coerced})

    elif op_key == "isnull":
        q = Q(**{f"{orm_path}__isnull": _to_bool(rule.get("value"))})

    else:
        py_val = _coerce_value(model, orm_path, rule.get("value"))
        if py_val is None and lookup != "isnull":
            # avoid generating X__icontains=None etc.
            return None
        key = orm_path if lookup == "" else f"{orm_path}__{lookup}"
        q = Q(**{key: py_val})

    # Negation (for neq or explicit negate)
    if op_key == "neq":
        q = ~q
    elif rule.get("negate"):
        q = ~q

    return q


def _combine_rules(model: type[Model],
                   rules: Iterable[Dict[str, Any]],
                   field_map: Mapping[str, str],
                   connector: str = "AND") -> Optional[Q]:
    """
    Combine multiple rule dicts into a single Q using AND/OR.
    Returns None if nothing valid.
    """
    qs: List[Q] = []
    for r in rules:
        q = _rule_to_q(model, r, field_map)
        if q is not None:
            qs.append(q)

    if not qs:
        return None

    combined = qs[0]
    for q in qs[1:]:
        combined = (combined & q) if connector == "AND" else (combined | q)
    return combined


# --- Public API --------------------------------------------------------------

def compute_audience_preview(
    and_rules: Iterable[Dict[str, Any]],
    or_rules: Iterable[Dict[str, Any]],
    base_qs: QuerySet,                       # e.g., Contact.objects.filter(tenant=...)
    field_map: Mapping[str, str] = FIELD_MAP
) -> int:
    """
    Return how many contacts match:
        (all AND rules) AND (at least one OR rule if any OR rules provided)
    If both groups are empty -> returns 0 (adjust if you want 'all').
    """
    model = base_qs.model

    and_q = _combine_rules(model, and_rules, field_map, connector="AND")
    or_q = _combine_rules(model, or_rules,  field_map, connector="OR")

    if and_q is None and or_q is None:
        return 0  # or: return base_qs.count()
    try:
        qs = base_qs
        if and_q is not None:
            qs = qs.filter(and_q)
        if or_q is not None:
            qs = qs.filter(or_q)

        return qs.count()
    except Exception as e:
        print(e)
        return 0


def compute_audience(
    and_rules: Iterable[Dict[str, Any]],
    or_rules: Iterable[Dict[str, Any]],
    base_qs: QuerySet,                       # e.g., Contact.objects.filter(tenant=...)
    field_map: Mapping[str, str] = FIELD_MAP,
    *,
    audience: Optional[Model] = None,        # If provided, we try to persist the result
    m2m_attr: str = "contacts",              # Audience.contacts (ManyToMany to Contact)
    replace: bool = True,                     # replace existing members (set), else add (add)
    m2m_through_defaults=None,
) -> QuerySet:
    """
    Build the final queryset using the same logic as preview and optionally
    persist it into an Audience object (M2M). Returns the queryset regardless.
    """
    model = base_qs.model

    and_q = _combine_rules(model, and_rules, field_map, connector="AND")
    or_q  = _combine_rules(model, or_rules,  field_map, connector="OR")

    if and_q is None and or_q is None:
        matched = base_qs.none()
    else:
        matched = base_qs
        if and_q is not None:
            matched = matched.filter(and_q)
        if or_q is not None:
            matched = matched.filter(or_q)

    # Persist selection into audience.m2m if requested
    if audience is not None and hasattr(audience, m2m_attr):
        rel = getattr(audience, m2m_attr)
        ids = list(matched.values_list("pk", flat=True))
        if replace:
            # Django supports through_defaults on set/add
            rel.set(ids, through_defaults=(m2m_through_defaults or {}))
        else:
            rel.add(*ids, through_defaults=(m2m_through_defaults or {}))
    return matched
