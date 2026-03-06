import inspect
from functools import lru_cache
from typing import Sequence, Type
from django.db import models

from django.db.models import Count
from django.apps import apps

MAX_FIELDS_PER_MODEL = 24
MAX_CHOICES = 8
MAX_TOPK = 8


def _safe_get_doc(cls: type) -> str:
    return (inspect.getdoc(cls) or "").strip()


def _field_line(f) -> str:
    name = getattr(f, "name", getattr(f, "attname", ""))
    ftype = f.get_internal_type() if hasattr(f, "get_internal_type") else f.__class__.__name__
    null = getattr(f, "null", False)
    blank = getattr(f, "blank", False)
    help_text = getattr(f, "help_text", "") or ""
    choices = getattr(f, "choices", None)
    parts = [ftype, "null" if null else "not null", "blank" if blank else "not blank"]
    if choices:
        ch = [c[0] for c in choices][:MAX_CHOICES]
        if len(choices) > MAX_CHOICES: ch.append("…")
        parts.append(f"choices={ch}")
    if help_text:
        parts.append(f"help='{help_text}'")
    return f"- {name}: " + ", ".join(parts)


def _iter_model_fields(model: Type[models.Model]):
    # data fields only (skip reverse/auto relations)
    for f in model._meta.get_fields():
        if not hasattr(f, "attname"):  # skip reverse relations
            continue
        yield f


def _topk_for_field(qs, field: str, k=MAX_TOPK):
    try:
        vals = (qs.values_list(field, flat=True)
                  .exclude(**{f"{field}__isnull": True})
                  .exclude(**{f"{field}": ""})
                  .annotate(_c=Count(field))
                  .order_by("-_c")[:k])
        vals = [v for v in vals if v is not None]
        return list(dict.fromkeys(vals))[:k]  # unique, keep order
    except Exception:
        return []


def _is_text_like(field) -> bool:
    return field.get_internal_type() in {"CharField", "TextField", "EmailField", "SlugField"}


def _is_relation(field) -> bool:
    from django.db.models import ForeignKey, ManyToManyField, OneToOneField
    return isinstance(field, (ForeignKey, ManyToManyField, OneToOneField))


@lru_cache(maxsize=256)
def _model_overview_static(app_label: str, model_name: str) -> str:
    # tenant-agnostic static bits (docstring, fields, constraints)
    model = apps.get_model(app_label, model_name)  # <-- use apps.get_model here
    lines = [
        f"Model: {app_label}.{model_name}",
        f"Docstring: {_safe_get_doc(model) or '(none)'}",
        "Fields:"
    ]

    count = 0
    for f in _iter_model_fields(model):
        if count >= MAX_FIELDS_PER_MODEL:
            lines.append(f"- … (truncated)")
            break
        lines.append(_field_line(f))
        count += 1

    meta = model._meta
    if getattr(meta, "unique_together", None):
        lines.append(f"Unique together: {list(meta.unique_together)}")
    if getattr(meta, "indexes", None):
        try:
            idx_names = [getattr(ix, "name", str(ix)) for ix in meta.indexes][:6]
            if idx_names:
                lines.append(f"Indexes: {idx_names}")
        except Exception:
            pass

    return "\n".join(lines)


def _model_overview_dynamic(model: Type[models.Model], tenant, depth: int) -> str:
    # tenant-scoped, short “top values” and relation cascade
    lines = []
    qs = getattr(model.objects, "filter")(tenant=tenant) if "tenant" in [f.name for f in _iter_model_fields(model)] else model.objects.all()
    # Top values for a few text fields
    shown = 0
    for f in _iter_model_fields(model):
        if shown >= 5: break
        if _is_text_like(f):
            top = _topk_for_field(qs, f.name)
            if top:
                lines.append(f"- {f.name} popular: {top[:MAX_TOPK]}")
                shown += 1

    # Cascade to related models (names only, depth guard)
    if depth > 0:
        related = []
        for f in model._meta.get_fields():
            if _is_relation(f):
                rel = f.related_model
                related.append(f"{rel._meta.app_label}.{rel.__name__}")
        if related:
            lines.append(f"Related models (depth {depth}): {sorted(set(related))[:8]}")
    return "\n".join(lines) or "(no tenant-scoped examples)"


def _render_model_awareness(domain_models: Sequence[Type[models.Model]], tenant, relation_depth: int) -> str:
    blocks = []
    for m in domain_models:
        app_label = m._meta.app_label
        model_name = m.__name__
        static = _model_overview_static(app_label, model_name)
        dynamic = _model_overview_dynamic(m, tenant, relation_depth)
        blocks.append(static + "\nTenant examples:\n" + dynamic)
    return "\n\n---\n\n".join(blocks)
