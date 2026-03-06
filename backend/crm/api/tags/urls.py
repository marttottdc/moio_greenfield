from django.urls import path

from crm.api.tags.views import TagsView, TagDetailView

urlpatterns = [
    path("", TagsView.as_view()),
    path("<int:tag_id>/", TagDetailView.as_view()),
]
