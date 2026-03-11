"""
Content validation for ActivityRecord.

- When record has type and type.schema: validate content with JSON Schema.
- When record has kind (and no type.schema): validate with PAYLOAD_MODEL_BY_KIND (Pydantic).
- Otherwise return content as-is.
"""

from __future__ import annotations

import json
from typing import Any, Dict, Mapping, Union

from jsonschema import Draft202012Validator, ValidationError as JsonSchemaValidationError

from crm.services.activity_payloads import PAYLOAD_MODEL_BY_KIND


def validate_content(
    record_or_type: Union[Any, None],
    content: Any,
    *,
    kind: str | None = None,
) -> Dict[str, Any]:
    """
    Validate and normalize activity content.

    Args:
        record_or_type: ActivityRecord instance or ActivityType instance (or None).
        content: Raw content dict or JSON string.
        kind: Optional kind to use when record has no type with schema.

    Returns:
        Validated content as a dict (ready for JSONField).

    Raises:
        TypeError: If content is not a dict or JSON string.
        ValueError: If kind is invalid for Pydantic path.
        JsonSchemaValidationError: If content fails type.schema validation.
    """
    if isinstance(content, str):
        content = json.loads(content)
    if not isinstance(content, Mapping):
        raise TypeError("content must be a dict or JSON object string")

    content = dict(content)
    activity_type = getattr(record_or_type, "type", record_or_type)
    type_schema = getattr(activity_type, "schema", None) if activity_type else None

    if type_schema and isinstance(type_schema, dict):
        validator = Draft202012Validator(type_schema)
        validator.validate(content)
        return content

    kind_value = getattr(record_or_type, "kind", None) or kind
    if kind_value and kind_value in PAYLOAD_MODEL_BY_KIND:
        model_cls = PAYLOAD_MODEL_BY_KIND[kind_value]
        return model_cls.model_validate(content).model_dump(mode="json")

    return content
