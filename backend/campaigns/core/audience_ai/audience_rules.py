from __future__ import annotations

from enum import Enum
from typing import Any, List, Optional, Union, Annotated

from pydantic import BaseModel, Field, ConfigDict, model_validator, ValidationError, ValidationInfo

# --- Domain enums -------------------------------------------------------------

class Op(str, Enum):
    between = "between"
    icontains  = "contains"
    iendswith  = "endswith"
    eq        = "="
    gt        = "gt"
    gte       = "gte"
    _in       = "in"        # "in" is fine as a value, just avoid as an identifier
    isfalse   = "isfalse"
    isnull    = "isnull"
    istrue    = "istrue"
    lt        = "lt"
    lte       = "lte"
    neq       = "neq"
    istartswith = "startswith"

# A "scalar" per your schema (including null). For "in", we need a non-null scalar list.
Scalar = Optional[Union[str, float, bool]]
ScalarList = List[Union[str, float, bool]]

# --- Rule object --------------------------------------------------------------


class Rule(BaseModel):
    """
    Mirrors:
      - additionalProperties: false
      - required: ["field", "op", "value", "value_to", "negate"]
      - value: anyOf [scalar|null, array-of-scalars]
      - value_to: scalar|null (must be provided for 'between')
      - negate: bool (always present)
    """
    model_config = ConfigDict(extra="forbid")

    field: str
    op: Op
    # Always present; may be null; for 'in' it must be a non-empty array of scalars.
    value: Union[Scalar, ScalarList]
    # Always present; may be null except when op == "between"
    value_to: Scalar = None
    # Always present
    negate: bool

    @model_validator(mode="after")
    def _validate_semantics(self) -> "Rule":
        # Context carries allowed_fields: set[str]
        # Usage: Rule.model_validate(payload, context={"allowed_fields": {...}})
        # or AudienceRules.model_validate(..., context={"allowed_fields": {...}})
        info: ValidationInfo = getattr(self, "__pydantic_validator_info__", None)  # populated by Pydantic
        allowed_fields = None
        if info and info.context:
            allowed_fields = info.context.get("allowed_fields")

        # 1) allowed_fields constraint (if provided)
        if allowed_fields is not None and self.field not in allowed_fields:
            raise ValueError(f'field="{self.field}" is not in allowed_fields: {sorted(allowed_fields)}')

        # 2) operator-specific constraints
        if self.op == Op.between:
            # value and value_to must both be scalars (value may be null in schema, but 'between' needs both)
            if isinstance(self.value, list):
                raise ValueError('For op="between", "value" must be a scalar, not a list.')
            if self.value is None or self.value_to is None:
                raise ValueError('For op="between", both "value" and "value_to" must be provided (not null).')

        elif self.op == Op._in:
            # value must be a non-empty array of scalars
            if not isinstance(self.value, list):
                raise ValueError('For op="in", "value" must be a non-empty array of scalars.')
            if len(self.value) == 0:
                raise ValueError('For op="in", "value" cannot be empty.')
            # Ensure items are scalars (no None)
            for i, item in enumerate(self.value):
                if item is None or isinstance(item, list) or isinstance(item, dict):
                    raise ValueError(f'For op="in", "value[{i}]" must be a scalar (str/number/bool).')

        else:
            # For all other ops, "value" must be scalar (can be null when the op doesn’t need it)
            if isinstance(self.value, list):
                raise ValueError(f'For op="{self.op}", "value" must be a scalar (not a list).')

        return self

# --- Top-level container ------------------------------------------------------


class AudienceRules(BaseModel):
    """
    Mirrors:
      name: "audience_rules" (name is out-of-band; this class represents the schema)
      schema:
        type: object
        additionalProperties: false
        properties:
          and: array of Rule, maxItems: 20
          or:  array of Rule, maxItems: 20
        required: ["and", "or"]
    """
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    # Use alias to serialize/parse with exact "and"/"or" keys
    and_: Annotated[List[Rule], Field(alias="and", max_length=20)]
    or_:  Annotated[List[Rule], Field(alias="or",  max_length=20)]

    # Keep keys present on dump even when values are None
    def model_dump_strict(self, **kwargs: Any) -> dict:
        """
        Helper to dump with None included (so every required key is present),
        matching your "all keys present" requirement.
        """
        return self.model_dump(by_alias=True, exclude_none=False, **kwargs)

#
