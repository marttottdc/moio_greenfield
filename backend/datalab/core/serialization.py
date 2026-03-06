"""
Serialization utilities for Data Lab.

Ensures all responses are JSON-safe:
- Converts pandas/numpy/decimal/date types
- Normalizes NaN/Inf to None
- Recursively handles lists/dicts
"""
from __future__ import annotations

import decimal
import math
from datetime import date, datetime
from typing import Any

import pandas as pd

try:
    import numpy as np
except ImportError:  # pragma: no cover - optional dependency
    np = None


def _is_nan_or_inf(value: Any) -> bool:
    """Return True if value is NaN or Inf (float or numpy)."""
    try:
        return math.isnan(value) or math.isinf(value)
    except Exception:
        return False


def serialize_for_json(obj: Any) -> Any:
    """
    Convert non-JSON-serializable types to JSON-safe values.

    Handles:
    - pandas.Timestamp, datetime/date -> ISO string
    - decimal.Decimal -> string
    - numpy integer/float/bool -> native Python types
    - NaN/Inf/None -> None
    - pd.NA / pd.isna() -> None
    - Nested dicts/lists/tuples recursively
    """
    # Normalize pandas NA/NaN/None up front
    try:
        if pd.isna(obj):
            return None
    except (TypeError, ValueError):
        pass

    # Scalars
    if obj is None:
        return None

    if isinstance(obj, (str, int, bool)):
        return obj

    if isinstance(obj, float):
        return None if _is_nan_or_inf(obj) else obj

    if isinstance(obj, decimal.Decimal):
        return str(obj)

    # Datetime / date
    if isinstance(obj, (pd.Timestamp, datetime)):
        return obj.isoformat()
    if isinstance(obj, date):
        return obj.isoformat()

    # Numpy scalars
    if np is not None:
        if isinstance(obj, np.integer):
            return int(obj)
        if isinstance(obj, np.floating):
            return None if _is_nan_or_inf(float(obj)) else float(obj)
        if isinstance(obj, np.bool_):
            return bool(obj)

    # Containers
    if isinstance(obj, dict):
        return {key: serialize_for_json(value) for key, value in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [serialize_for_json(item) for item in obj]

    # Fallback to string
    try:
        return str(obj)
    except Exception:
        return None
