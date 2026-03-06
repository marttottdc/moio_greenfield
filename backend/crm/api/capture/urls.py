from django.urls import path

from crm.api.capture.views import (
    CaptureEntriesView,
    CaptureEntryDetailView,
    CaptureEntryApproveView,
    CaptureEntryNoteOnlyView,
    CaptureEntrySplitView,
    CaptureEntryRejectView,
    CaptureClassifySyncView,
    CaptureEntryApplySyncView,
)


urlpatterns = [
    path("entries/", CaptureEntriesView.as_view()),
    path("entries/<uuid:entry_id>/", CaptureEntryDetailView.as_view()),
    path("entries/<uuid:entry_id>/review/approve/", CaptureEntryApproveView.as_view()),
    path("entries/<uuid:entry_id>/review/note_only/", CaptureEntryNoteOnlyView.as_view()),
    path("entries/<uuid:entry_id>/review/split/", CaptureEntrySplitView.as_view()),
    path("entries/<uuid:entry_id>/review/reject/", CaptureEntryRejectView.as_view()),
    path("classify-sync/", CaptureClassifySyncView.as_view()),
    path("entries/<uuid:entry_id>/apply-sync/", CaptureEntryApplySyncView.as_view()),
]

