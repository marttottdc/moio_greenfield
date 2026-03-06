from django.urls import path

from crm.api.public_views import (
    TicketCommentsView,
    TicketDetailView,
    TicketListCreateView,
    TicketSummaryView,
)

urlpatterns = [
    path("", TicketListCreateView.as_view()),
    path("summary/", TicketSummaryView.as_view()),
    path("<uuid:ticket_id>/", TicketDetailView.as_view()),
    path("<uuid:ticket_id>/comments/", TicketCommentsView.as_view()),
]
