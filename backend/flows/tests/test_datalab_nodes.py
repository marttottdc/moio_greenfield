"""Tests for Data Lab flow node executors: datalab_ingest, datalab_resultset_get."""
import socket
from unittest.mock import patch

from django.test import TestCase

from flows.core.registry import get_executor
from portal.models import Tenant

# DataLab models (optional: skip tests if datalab not installed)
try:
    from datalab.core.models import FileAsset, ResultSet, ResultSetOrigin, ResultSetStorage
    DATALAB_AVAILABLE = True
except ImportError:
    DATALAB_AVAILABLE = False


def _ctx(tenant_id):
    return {"tenant_id": str(tenant_id)}


class DatalabIngestNodeTests(TestCase):
    def setUp(self):
        if not DATALAB_AVAILABLE:
            self.skipTest("datalab not available")
        self.tenant = Tenant.objects.create(
            nombre="Test Tenant",
            enabled=True,
            domain="test.local",
        )
        self.executor = get_executor("datalab_ingest")

    def test_ingest_requires_tenant_id(self):
        node = {"id": "n1", "config": {"file_id": None}}
        result = self.executor(node, {}, {})
        self.assertFalse(result.get("success"))
        self.assertIn("tenant_id", result.get("error", "").lower())

    def test_ingest_requires_one_of_file_id_url_or_base64(self):
        node = {"id": "n1", "config": {}}
        result = self.executor(node, {}, _ctx(self.tenant.id))
        self.assertFalse(result.get("success"))
        self.assertIn("file_id", result.get("error", ""))

    def test_ingest_pass_through_by_file_id(self):
        asset = FileAsset.objects.create(
            tenant=self.tenant,
            storage_key="datalab/files/test/fake.csv",
            filename="fake.csv",
            content_type="text/csv",
            size=100,
            uploaded_by=None,
            metadata={},
        )
        node = {"id": "n1", "config": {"file_id": str(asset.id)}}
        result = self.executor(node, {}, _ctx(self.tenant.id))
        self.assertTrue(result.get("success"), result)
        self.assertEqual(result.get("file_id"), str(asset.id))
        self.assertEqual(result.get("filename"), "fake.csv")
        self.assertEqual(result.get("content_type"), "text/csv")
        self.assertEqual(result.get("size"), 100)
        self.assertEqual(result.get("storage_key"), asset.storage_key)

    def test_ingest_file_id_not_found_returns_error(self):
        import uuid
        node = {"id": "n1", "config": {"file_id": str(uuid.uuid4())}}
        result = self.executor(node, {}, _ctx(self.tenant.id))
        self.assertFalse(result.get("success"))
        self.assertIn("not found", result.get("error", "").lower())

    @patch("urllib.request.urlopen")
    def test_ingest_rejects_disallowed_url_scheme(self, mock_urlopen):
        node = {"id": "n1", "config": {"url": "file:///etc/passwd"}}
        result = self.executor(node, {}, _ctx(self.tenant.id))
        self.assertFalse(result.get("success"))
        self.assertIn("invalid url", result.get("error", "").lower())
        self.assertIn("http and https", result.get("error", "").lower())
        mock_urlopen.assert_not_called()

    @patch("urllib.request.urlopen")
    def test_ingest_rejects_private_ip_url(self, mock_urlopen):
        node = {"id": "n1", "config": {"url": "http://169.254.169.254/latest/meta-data/"}}
        result = self.executor(node, {}, _ctx(self.tenant.id))
        self.assertFalse(result.get("success"))
        self.assertIn("invalid url", result.get("error", "").lower())
        self.assertIn("non-public ip", result.get("error", "").lower())
        mock_urlopen.assert_not_called()

    @patch("flows.core.registry.socket.getaddrinfo")
    @patch("urllib.request.urlopen")
    def test_ingest_rejects_hostname_resolving_to_private_ip(self, mock_urlopen, mock_getaddrinfo):
        mock_getaddrinfo.return_value = [
            (socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", ("10.0.0.42", 80))
        ]
        node = {"id": "n1", "config": {"url": "http://internal.example.local/test.csv"}}
        result = self.executor(node, {}, _ctx(self.tenant.id))
        self.assertFalse(result.get("success"))
        self.assertIn("invalid url", result.get("error", "").lower())
        self.assertIn("non-public ip", result.get("error", "").lower())
        mock_urlopen.assert_not_called()

    @patch("flows.core.registry.socket.getaddrinfo")
    @patch("urllib.request.urlopen")
    def test_ingest_public_url_attempts_download(self, mock_urlopen, mock_getaddrinfo):
        from urllib.error import URLError

        mock_getaddrinfo.return_value = [
            (socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", ("93.184.216.34", 443))
        ]
        mock_urlopen.side_effect = URLError("network disabled in tests")

        node = {"id": "n1", "config": {"url": "https://example.com/test.csv"}}
        result = self.executor(node, {}, _ctx(self.tenant.id))

        self.assertFalse(result.get("success"))
        self.assertIn("failed to download url", result.get("error", "").lower())
        mock_urlopen.assert_called_once_with("https://example.com/test.csv", timeout=30)


class DatalabResultsetGetNodeTests(TestCase):
    def setUp(self):
        if not DATALAB_AVAILABLE:
            self.skipTest("datalab not available")
        self.tenant = Tenant.objects.create(
            nombre="Test Tenant",
            enabled=True,
            domain="test.local",
        )
        self.executor = get_executor("datalab_resultset_get")

    def test_resultset_get_requires_tenant_id(self):
        node = {"id": "n1", "config": {"resultset_id": None}}
        result = self.executor(node, {}, {})
        self.assertFalse(result.get("success"))
        self.assertIn("tenant_id", result.get("error", "").lower())

    def test_resultset_get_requires_resultset_id(self):
        node = {"id": "n1", "config": {}}
        result = self.executor(node, {}, _ctx(self.tenant.id))
        self.assertFalse(result.get("success"))
        self.assertIn("resultset_id", result.get("error", ""))

    def test_resultset_get_returns_metadata_and_preview(self):
        resultset = ResultSet.objects.create(
            tenant=self.tenant,
            origin=ResultSetOrigin.IMPORT,
            schema_json={"columns": [{"name": "a", "type": "string", "nullable": True}]},
            row_count=2,
            storage=ResultSetStorage.MEMORY,
            preview_json=[{"a": "1"}, {"a": "2"}],
            is_json_object=False,
            created_by=None,
        )
        node = {
            "id": "n1",
            "config": {
                "resultset_id": str(resultset.id),
                "include_preview": True,
                "preview_limit": 10,
            },
        }
        result = self.executor(node, {}, _ctx(self.tenant.id))
        self.assertTrue(result.get("success"), result)
        self.assertEqual(result.get("resultset_id"), str(resultset.id))
        self.assertEqual(result.get("row_count"), 2)
        self.assertEqual(result.get("schema_json"), resultset.schema_json)
        self.assertEqual(result.get("origin"), ResultSetOrigin.IMPORT)
        self.assertEqual(len(result.get("preview_json", [])), 2)
        self.assertEqual(result["preview_json"][0], {"a": "1"})
