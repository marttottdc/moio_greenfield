from django.urls import path

from crm.api.contacts.views import (
    ContactDetailView,
    ContactExportView,
    ContactPromoteView,
    ContactsSummaryView,
    ContactsView,
)

urlpatterns = [
    path("summary/", ContactsSummaryView.as_view()),
    path("", ContactsView.as_view()),
    path("export/", ContactExportView.as_view()),
    path("<uuid:contact_id>/", ContactDetailView.as_view()),
    path("<uuid:contact_id>/promote/", ContactPromoteView.as_view()),
]
