from django.urls import path

from crm.api.activities.views import (
    ActivitiesView,
    ActivityDetailView,
    ActivitySuggestionsView,
    ActivitySuggestionAcceptView,
    ActivitySuggestionDismissView,
)

urlpatterns = [
    path("", ActivitiesView.as_view()),
    path("<uuid:activity_id>/", ActivityDetailView.as_view()),
    path("suggestions/", ActivitySuggestionsView.as_view()),
    path("suggestions/<uuid:suggestion_id>/accept/", ActivitySuggestionAcceptView.as_view()),
    path("suggestions/<uuid:suggestion_id>/dismiss/", ActivitySuggestionDismissView.as_view()),
]
