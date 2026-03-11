from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

from django.test import SimpleTestCase

from crm.core.activity_capture_contract import ClassificationOutput
from crm.services.activity_capture_service import OpenAIConfig, classify_entry_via_openai


def _valid_payload():
    return {
        "summary": "Follow up tomorrow",
        "channel": "OTHER",
        "direction": "INTERNAL",
        "outcome": "UNKNOWN",
        "suggested_activities": [],
        "suggest_links": [],
        "needs_review": False,
        "review_reasons": [],
        "confidence": 0.9,
    }


class ClassifyEntryViaOpenAITests(SimpleTestCase):
    def _entry(self):
        return SimpleNamespace(
            tenant=SimpleNamespace(nombre="Tenant"),
            actor=SimpleNamespace(preferences={"timezone": "UTC"}),
            anchor_model="crm.deal",
            anchor_id="11111111-1111-1111-1111-111111111111",
            raw_text="follow up tomorrow",
        )

    @patch("crm.services.activity_capture_service._resolve_anchor_label", return_value="Deal ABC")
    @patch(
        "crm.services.activity_capture_service.get_openai_config_for_tenant",
        return_value=OpenAIConfig(api_key="k", default_model="gpt-4o-mini", max_retries=1),
    )
    def test_structured_one_step_success(self, _cfg_mock, _label_mock):
        class FakeMoioOpenai:
            def __init__(self, api_key, default_model, max_retries=5, **kwargs):
                self.default_model = default_model

            @staticmethod
            def model_supports_structured_outputs(model: str) -> bool:
                return True

            def structured_parse(self, **kwargs):
                return ClassificationOutput.model_validate(_valid_payload())

        with patch("moio_platform.lib.openai_gpt_api.MoioOpenai", FakeMoioOpenai):
            out = classify_entry_via_openai(entry=self._entry())
            self.assertIsInstance(out, ClassificationOutput)
            self.assertEqual(out.summary, "Follow up tomorrow")

    @patch("crm.services.activity_capture_service._resolve_anchor_label", return_value="Deal ABC")
    @patch(
        "crm.services.activity_capture_service.get_openai_config_for_tenant",
        return_value=OpenAIConfig(api_key="k", default_model="gpt-4o-mini", max_retries=1),
    )
    def test_two_step_repair_path(self, _cfg_mock, _label_mock):
        class FakeMoioOpenai:
            def __init__(self, api_key, default_model, max_retries=5, **kwargs):
                self.default_model = default_model
                self.calls = 0

            @staticmethod
            def model_supports_structured_outputs(model: str) -> bool:
                return True

            def structured_parse(self, data, **kwargs):
                self.calls += 1
                if data == "":
                    raise ValueError("structured_failed")
                return ClassificationOutput.model_validate(_valid_payload())

            def json_response(self, *args, **kwargs):
                return '{"classification":"follow_up","next_contact_date":"2026-03-06T15:57:58Z"}'

        with patch("moio_platform.lib.openai_gpt_api.MoioOpenai", FakeMoioOpenai):
            out = classify_entry_via_openai(entry=self._entry())
            self.assertIsInstance(out, ClassificationOutput)
            self.assertEqual(out.confidence, 0.9)

    @patch("crm.services.activity_capture_service._resolve_anchor_label", return_value="Deal ABC")
    @patch(
        "crm.services.activity_capture_service.get_openai_config_for_tenant",
        return_value=OpenAIConfig(api_key="k", default_model="gpt-4o-mini", max_retries=1),
    )
    def test_fallback_when_repair_fails(self, _cfg_mock, _label_mock):
        class FakeMoioOpenai:
            def __init__(self, api_key, default_model, max_retries=5, **kwargs):
                self.default_model = default_model

            @staticmethod
            def model_supports_structured_outputs(model: str) -> bool:
                return True

            def structured_parse(self, **kwargs):
                raise ValueError("structured_failed")

            def json_response(self, *args, **kwargs):
                return Exception("json_mode_failed")

        with patch("moio_platform.lib.openai_gpt_api.MoioOpenai", FakeMoioOpenai):
            out = classify_entry_via_openai(entry=self._entry())
            self.assertTrue(out.needs_review)
            self.assertEqual(out.confidence, 0.0)

    @patch("crm.services.activity_capture_service._resolve_anchor_label", return_value="Deal ABC")
    @patch(
        "crm.services.activity_capture_service.get_openai_config_for_tenant",
        return_value=OpenAIConfig(api_key="k", default_model="gpt-4-turbo-preview", max_retries=1),
    )
    def test_unsupported_model_raises(self, _cfg_mock, _label_mock):
        class FakeMoioOpenai:
            def __init__(self, api_key, default_model, max_retries=5, **kwargs):
                self.default_model = default_model

            @staticmethod
            def model_supports_structured_outputs(model: str) -> bool:
                return False

        with patch("moio_platform.lib.openai_gpt_api.MoioOpenai", FakeMoioOpenai):
            with self.assertRaisesRegex(ValueError, "Configured Model does not support structured Outputs"):
                classify_entry_via_openai(entry=self._entry())

