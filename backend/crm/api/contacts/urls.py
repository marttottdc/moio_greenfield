from django.urls import path

from crm.api.public_views import ContactDetailView, ContactExportView, ContactsView, ContactsSummaryView
from crm.api.contacts.views import ContactPromoteView

urlpatterns = [
    path("summary/", ContactsSummaryView.as_view()),
    path("", ContactsView.as_view()),
    path("export/", ContactExportView.as_view()),
    path("<uuid:contact_id>/", ContactDetailView.as_view()),
    path("<uuid:contact_id>/promote/", ContactPromoteView.as_view()),
]
