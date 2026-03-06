from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase
from rest_framework import status

from crm.api.activities.views import ActivitiesView, ActivityDetailView


class ActivitiesViewValidationTests(SimpleTestCase):
    def test_post_returns_400_when_content_validation_fails(self):
        view = ActivitiesView()
        request = SimpleNamespace(
            user=SimpleNamespace(tenant=object(), is_authenticated=False),
            data={"kind": "task", "content": "invalid"},
        )

        with patch(
            "crm.api.activities.views._normalize_content",
            side_effect=ValueError("content is invalid"),
        ):
            response = view.post(request)

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["error"], "invalid_request")


class ActivityDetailViewValidationTests(SimpleTestCase):
    def test_patch_returns_400_when_content_validation_fails(self):
        view = ActivityDetailView()
        activity = SimpleNamespace(kind="task", type=None, tenant=object(), save=MagicMock())
        request = SimpleNamespace(data={"content": "invalid"})

        with (
            patch.object(view, "_get_activity", return_value=activity),
            patch(
                "crm.api.activities.views._normalize_content",
                side_effect=ValueError("content is invalid"),
            ),
        ):
            response = view.patch(request, activity_id="activity-id")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["error"], "invalid_request")
        activity.save.assert_not_called()
