from django.urls import path

from crm.api.contact_types.views import ContactTypesView, ContactTypeDetailView

urlpatterns = [
    path("", ContactTypesView.as_view()),
    path("<uuid:contact_type_id>/", ContactTypeDetailView.as_view()),
]
