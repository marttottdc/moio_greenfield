from django.urls import path

from crm.api.timeline.views import TimelineView


urlpatterns = [
    path("", TimelineView.as_view()),
]

