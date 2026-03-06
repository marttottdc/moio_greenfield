from __future__ import annotations

from datetime import datetime, timezone as dt_timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase

from crm.api.capture.views import CaptureEntriesView


class CaptureEntriesViewTests(SimpleTestCase):
    @patch("crm.api.capture.views.classify_capture_entry")
    @patch("crm.api.capture.views.transaction.on_commit")
    @patch("crm.api.capture.views.create_capture_entry")
    def test_post_schedules_classification_for_new_entry(
        self, create_capture_entry_mock, on_commit_mock, classify_task_mock
    ):
        entry = SimpleNamespace(
            id="11111111-1111-1111-1111-111111111111",
            anchor_model="crm.deal",
            anchor_id="22222222-2222-2222-2222-222222222222",
            actor_id="33333333-3333-3333-3333-333333333333",
            raw_text="call tomorrow",
            raw_source="manual_text",
            channel_hint=None,
            visibility="internal",
            status="captured",
            llm_model="gpt-4o-mini",
            prompt_version="v2.0",
            classification=None,
            summary=None,
            confidence=None,
            needs_review=False,
            review_reasons=[],
            final=None,
            applied_refs=None,
            idempotency_key=None,
            created_at=datetime(2026, 2, 17, 12, 0, tzinfo=dt_timezone.utc),
            updated_at=datetime(2026, 2, 17, 12, 0, tzinfo=dt_timezone.utc),
        )
        create_capture_entry_mock.return_value = (entry, True)
        on_commit_mock.side_effect = lambda fn: fn()

        view = CaptureEntriesView()
        request = SimpleNamespace(
            user=SimpleNamespace(is_authenticated=True, tenant=object()),
            data={"raw_text": "call tomorrow", "anchor_model": "crm.deal", "anchor_id": entry.anchor_id},
            query_params={},
        )

        resp = view.post(request)

        self.assertEqual(resp.status_code, 201)
        classify_task_mock.delay.assert_called_once()

    @patch("crm.api.capture.views.classify_capture_entry")
    @patch("crm.api.capture.views.transaction.on_commit")
    @patch("crm.api.capture.views.create_capture_entry")
    def test_post_does_not_schedule_classification_for_existing_entry(
        self, create_capture_entry_mock, on_commit_mock, classify_task_mock
    ):
        entry = SimpleNamespace(
            id="11111111-1111-1111-1111-111111111111",
            anchor_model="crm.deal",
            anchor_id="22222222-2222-2222-2222-222222222222",
            actor_id="33333333-3333-3333-3333-333333333333",
            raw_text="call tomorrow",
            raw_source="manual_text",
            channel_hint=None,
            visibility="internal",
            status="captured",
            llm_model="gpt-4o-mini",
            prompt_version="v2.0",
            classification=None,
            summary=None,
            confidence=None,
            needs_review=False,
            review_reasons=[],
            final=None,
            applied_refs=None,
            idempotency_key="same",
            created_at=datetime(2026, 2, 17, 12, 0, tzinfo=dt_timezone.utc),
            updated_at=datetime(2026, 2, 17, 12, 0, tzinfo=dt_timezone.utc),
        )
        create_capture_entry_mock.return_value = (entry, False)

        view = CaptureEntriesView()
        request = SimpleNamespace(
            user=SimpleNamespace(is_authenticated=True, tenant=object()),
            data={"raw_text": "call tomorrow", "anchor_model": "crm.deal", "anchor_id": entry.anchor_id, "idempotency_key": "same"},
            query_params={},
        )

        resp = view.post(request)

        self.assertEqual(resp.status_code, 200)
        on_commit_mock.assert_not_called()
        classify_task_mock.delay.assert_not_called()

