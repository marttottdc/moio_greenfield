from django.urls import path

from crm.api.knowledge.views import KnowledgeListView, KnowledgeDetailView

urlpatterns = [
    path("", KnowledgeListView.as_view()),
    path("<uuid:item_id>/", KnowledgeDetailView.as_view()),
]
