from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase, TestCase
from pydantic import BaseModel, ValidationError

from crm.api.activities.views import (
    ActivitySuggestionAcceptView,
    ActivitySuggestionDismissView,
    ActivitySuggestionsView,
)
from crm.models import ActivityKind, ActivitySuggestionStatus, ActivityTypeCategory
from crm.services.activity_suggestion_service import accept_suggestion, dismiss_suggestion


class ActivitySuggestionsViewTests(SimpleTestCase):
    def test_get_without_status_param_does_not_apply_status_filter(self):
        view = ActivitySuggestionsView()
        queryset = MagicMock()
        queryset.order_by.return_value = queryset
        request = SimpleNamespace(query_params={})

        with (
            patch.object(view, "_base_queryset", return_value=queryset),
            patch.object(view, "_paginate", return_value={"suggestions": [], "pagination": {}}),
        ):
            response = view.get(request)

        queryset.filter.assert_not_called()
        queryset.order_by.assert_called_once_with("-suggested_at")
        self.assertEqual(response.status_code, 200)

    def test_get_with_status_param_applies_status_filter(self):
        view = ActivitySuggestionsView()
        queryset = MagicMock()
        queryset.filter.return_value = queryset
        queryset.order_by.return_value = queryset
        request = SimpleNamespace(query_params={"status": "pending"})

        with (
            patch.object(view, "_base_queryset", return_value=queryset),
            patch.object(view, "_paginate", return_value={"suggestions": [], "pagination": {}}),
        ):
            response = view.get(request)

        queryset.filter.assert_called_once_with(status="pending")
        queryset.order_by.assert_called_once_with("-suggested_at")
        self.assertEqual(response.status_code, 200)


class ActivitySuggestionDismissViewTests(SimpleTestCase):
    def test_dismiss_returns_400_for_non_pending_suggestion(self):
        view = ActivitySuggestionDismissView()
        request = SimpleNamespace(user=SimpleNamespace(tenant=object()))

        with patch(
            "crm.api.activities.views.dismiss_suggestion",
            side_effect=ValueError("Suggestion is not pending: accepted"),
        ):
            response = view.post(request, suggestion_id="123")

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data["error"], "invalid_state")


class ActivitySuggestionAcceptViewTests(SimpleTestCase):
    def test_accept_returns_400_for_invalid_overrides_payload(self):
        view = ActivitySuggestionAcceptView()
        request = SimpleNamespace(user=SimpleNamespace(tenant=object()), data={"overrides": "bad"})

        with patch(
            "crm.api.activities.views.accept_suggestion",
            side_effect=ValueError("overrides must be an object"),
        ):
            response = view.post(request, suggestion_id="123")

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data["error"], "invalid_state")

    def test_accept_returns_400_for_pydantic_validation_error(self):
        view = ActivitySuggestionAcceptView()
        request = SimpleNamespace(user=SimpleNamespace(tenant=object()), data={"overrides": {}})

        class _Payload(BaseModel):
            required_field: str

        with self.assertRaises(ValidationError) as captured:
            _Payload.model_validate({})

        with patch(
            "crm.api.activities.views.accept_suggestion",
            side_effect=captured.exception,
        ):
            response = view.post(request, suggestion_id="123")

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data["error"], "invalid_state")


class AcceptSuggestionServiceTests(TestCase):
    def test_accept_rejects_non_mapping_overrides(self):
        with self.assertRaisesRegex(ValueError, "overrides must be an object"):
            accept_suggestion("abc", user=SimpleNamespace(), overrides="bad")

    @patch("crm.services.activity_suggestion_service.create_activity")
    @patch("crm.services.activity_suggestion_service.ActivityType.objects.get")
    @patch("crm.services.activity_suggestion_service.get_object_or_404")
    @patch("crm.services.activity_suggestion_service.ActivitySuggestion.objects.select_for_update")
    def test_accept_non_task_type_defaults_kind_to_other(
        self,
        select_for_update_mock,
        get_object_or_404_mock,
        activity_type_get_mock,
        create_activity_mock,
    ):
        queryset = MagicMock()
        select_for_update_mock.return_value = queryset
        queryset.filter.return_value = queryset

        suggestion = SimpleNamespace(
            status=ActivitySuggestionStatus.PENDING,
            proposed_fields={"content": {"summary": "Call next week"}},
            type_key="call.outbound",
            tenant=object(),
            target_contact_id=None,
            target_client_id=None,
            target_deal_id=None,
            reason="No activity in 14 days",
            save=MagicMock(),
        )
        get_object_or_404_mock.return_value = suggestion
        activity_type_get_mock.return_value = SimpleNamespace(
            category=ActivityTypeCategory.MEETING,
        )
        create_activity_mock.return_value = SimpleNamespace(pk="activity-id")

        accept_suggestion("abc", user=SimpleNamespace())

        self.assertEqual(create_activity_mock.call_args.kwargs["kind"], ActivityKind.OTHER)


class DismissSuggestionServiceTests(TestCase):
    @patch("crm.services.activity_suggestion_service.get_object_or_404")
    @patch("crm.services.activity_suggestion_service.ActivitySuggestion.objects.select_for_update")
    def test_dismiss_raises_for_non_pending_state(self, select_for_update_mock, get_object_or_404_mock):
        queryset = MagicMock()
        select_for_update_mock.return_value = queryset
        queryset.filter.return_value = queryset
        suggestion = MagicMock()
        suggestion.status = ActivitySuggestionStatus.ACCEPTED
        get_object_or_404_mock.return_value = suggestion

        with self.assertRaises(ValueError):
            dismiss_suggestion("abc")

    @patch("crm.services.activity_suggestion_service.get_object_or_404")
    @patch("crm.services.activity_suggestion_service.ActivitySuggestion.objects.select_for_update")
    def test_dismiss_marks_pending_suggestion_as_dismissed(self, select_for_update_mock, get_object_or_404_mock):
        queryset = MagicMock()
        select_for_update_mock.return_value = queryset
        queryset.filter.return_value = queryset
        suggestion = MagicMock()
        suggestion.status = ActivitySuggestionStatus.PENDING
        get_object_or_404_mock.return_value = suggestion

        dismiss_suggestion("abc")

        self.assertEqual(suggestion.status, ActivitySuggestionStatus.DISMISSED)
        suggestion.save.assert_called_once_with(update_fields=["status"])
