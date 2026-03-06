from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

from django.test import SimpleTestCase
from jsonschema import ValidationError as JsonSchemaValidationError

from crm.services.activity_service import _normalize_content


class NormalizeContentTests(SimpleTestCase):
    def test_other_kind_reraises_when_activity_type_schema_validation_fails(self):
        activity_type = SimpleNamespace(schema={"type": "object"})
        with patch(
            "crm.services.activity_service.validate_content",
            side_effect=JsonSchemaValidationError("invalid"),
        ):
            with self.assertRaises(JsonSchemaValidationError):
                _normalize_content({"foo": "bar"}, kind="other", activity_type=activity_type)
