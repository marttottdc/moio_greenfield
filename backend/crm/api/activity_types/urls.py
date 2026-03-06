from django.urls import path

from crm.api.activity_types.views import ActivityTypesView, ActivityTypeDetailView

urlpatterns = [
    path("", ActivityTypesView.as_view()),
    path("<uuid:type_id>/", ActivityTypeDetailView.as_view()),
]
