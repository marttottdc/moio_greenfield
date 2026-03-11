from __future__ import annotations

from datetime import datetime, timedelta, timezone as dt_timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase

from crm.models import CaptureAnchorModel
from crm.services.activity_capture_service import apply_capture_entry_to_activities


class ApplyCaptureEntryToActivitiesTests(SimpleTestCase):
    @patch("crm.services.activity_capture_service.has_calendar_conflicts", return_value=False)
    @patch("crm.services.activity_service.activity_manager", new_callable=MagicMock)
    def test_apply_creates_task_activityrecord_from_suggested_activities(self, activity_manager_mock, _conflicts_mock):
        due = datetime(2026, 2, 18, 9, 0, tzinfo=dt_timezone.utc)
        entry = SimpleNamespace(
            tenant=SimpleNamespace(id="tenant-id"),
            anchor_model=CaptureAnchorModel.DEAL,
            anchor_id="11111111-1111-1111-1111-111111111111",
            raw_text="follow up tomorrow 9am",
            visibility="internal",
            summary="Follow up tomorrow 9am",
            classification={
                "summary": "Follow up tomorrow 9am",
                "suggested_activities": [
                    {
                        "kind": "task",
                        "title": "Follow up",
                        "proposed_due_at": due.isoformat().replace("+00:00", "Z"),
                        "priority": "HIGH",
                    }
                ],
            },
            final=None,
        )
        actor = SimpleNamespace(preferences={"timezone": "UTC"})

        created_activity = SimpleNamespace(id="activity-1", save=MagicMock())
        activity_manager_mock.create_activity.return_value = created_activity

        refs = apply_capture_entry_to_activities(entry=entry, actor=actor)

        self.assertEqual(refs["activity_record_ids"], ["activity-1"])
        kwargs = activity_manager_mock.create_activity.call_args.args[0]
        self.assertEqual(kwargs["kind"], "task")
        self.assertEqual(kwargs["title"], "Follow up")
        self.assertEqual(kwargs["status"], "planned")
        self.assertEqual(kwargs["deal_id"], entry.anchor_id)

    @patch("crm.services.activity_capture_service.has_calendar_conflicts", return_value=False)
    @patch("crm.services.activity_service.activity_manager", new_callable=MagicMock)
    def test_apply_creates_event_from_suggested_activities(self, activity_manager_mock, _conflicts_mock):
        start = datetime(2026, 2, 18, 10, 0, tzinfo=dt_timezone.utc)
        end = start + timedelta(minutes=30)
        entry = SimpleNamespace(
            tenant=SimpleNamespace(id="tenant-id"),
            anchor_model=CaptureAnchorModel.CONTACT,
            anchor_id="22222222-2222-2222-2222-222222222222",
            raw_text="meeting tomorrow 10",
            visibility="internal",
            summary="Meeting tomorrow 10",
            classification={
                "summary": "Meeting tomorrow 10",
                "suggested_activities": [
                    {
                        "kind": "event",
                        "title": "Meeting",
                        "proposed_start_at": start.isoformat().replace("+00:00", "Z"),
                        "proposed_end_at": end.isoformat().replace("+00:00", "Z"),
                        "status": "planned",
                    }
                ],
            },
            final=None,
        )
        actor = SimpleNamespace(preferences={"timezone": "UTC"})

        created_activity = SimpleNamespace(id="activity-2", save=MagicMock())
        activity_manager_mock.create_activity.return_value = created_activity

        refs = apply_capture_entry_to_activities(entry=entry, actor=actor)

        self.assertEqual(refs["activity_record_ids"], ["activity-2"])
        kwargs = activity_manager_mock.create_activity.call_args.args[0]
        self.assertEqual(kwargs["kind"], "event")
        self.assertEqual(kwargs["title"], "Meeting")

