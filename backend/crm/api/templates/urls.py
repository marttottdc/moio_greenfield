from django.urls import path

from crm.api.public_views import TemplateListView

urlpatterns = [
    path("", TemplateListView.as_view()),
]
