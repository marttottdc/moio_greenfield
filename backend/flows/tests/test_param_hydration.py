"""Tests for Flow Script param hydration: $datalab_resultset resolution."""
from django.test import TestCase

from flows.scripts.param_hydration import resolve_datalab_param_refs
from portal.models import Tenant

try:
    from datalab.core.models import ResultSet, ResultSetOrigin, ResultSetStorage
    DATALAB_AVAILABLE = True
except ImportError:
    DATALAB_AVAILABLE = False


class ParamHydrationTests(TestCase):
    def setUp(self):
        if not DATALAB_AVAILABLE:
            self.skipTest("datalab not available")
        self.tenant = Tenant.objects.create(
            nombre="Hydration Tenant",
            enabled=True,
            domain="hydration.test",
        )

    def test_empty_tenant_id_returns_payload_unchanged(self):
        out = resolve_datalab_param_refs({"a": 1}, "")
        self.assertEqual(out, {"a": 1})

    def test_none_tenant_id_returns_payload_unchanged(self):
        out = resolve_datalab_param_refs({"a": 1}, None)
        self.assertEqual(out, {"a": 1})

    def test_payload_without_ref_unchanged(self):
        payload = {"foo": "bar", "nested": {"b": 2}}
        out = resolve_datalab_param_refs(payload, str(self.tenant.id))
        self.assertEqual(out, payload)

    def test_resolves_single_datalab_resultset_ref(self):
        resultset = ResultSet.objects.create(
            tenant=self.tenant,
            origin=ResultSetOrigin.IMPORT,
            schema_json={"columns": [{"name": "x", "type": "string"}]},
            row_count=1,
            storage=ResultSetStorage.MEMORY,
            preview_json=[{"x": "hello"}],
            is_json_object=False,
            created_by=None,
        )
        payload = {
            "data": {"$datalab_resultset": {"id": str(resultset.id), "mode": "preview", "limit": 10}},
        }
        out = resolve_datalab_param_refs(payload, str(self.tenant.id))
        self.assertIn("data", out)
        self.assertEqual(out["data"]["resultset_id"], str(resultset.id))
        self.assertEqual(out["data"]["row_count"], 1)
        self.assertEqual(out["data"]["schema_json"], resultset.schema_json)
        self.assertEqual(out["data"]["preview_json"], [{"x": "hello"}])

    def test_missing_id_in_ref_returns_error_in_resolved(self):
        payload = {"ref": {"$datalab_resultset": {"mode": "preview"}}}
        out = resolve_datalab_param_refs(payload, str(self.tenant.id))
        self.assertIn("ref", out)
        self.assertIn("error", out["ref"])
        self.assertIn("Missing id", out["ref"]["error"])

    def test_nonexistent_resultset_returns_error_in_resolved(self):
        import uuid
        payload = {"ref": {"$datalab_resultset": {"id": str(uuid.uuid4()), "mode": "preview"}}}
        out = resolve_datalab_param_refs(payload, str(self.tenant.id))
        self.assertIn("ref", out)
        self.assertIn("error", out["ref"])
        self.assertIn("not found", out["ref"]["error"].lower())
