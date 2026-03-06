from django.urls import path

from crm.api.public_views import (
    CommunicationsChannelsView,
    CommunicationsConversationDetailView,
    CommunicationsConversationMarkReadView,
    CommunicationsConversationMessagesView,
    CommunicationsConversationsView,
    CommunicationsSummaryView,
    CommunicationsWhatsappLogsView,
)

urlpatterns = [
    path("summary/", CommunicationsSummaryView.as_view()),
    path("conversations/", CommunicationsConversationsView.as_view()),
    path("conversations/<str:session_id>/", CommunicationsConversationDetailView.as_view()),
    path(
        "conversations/<str:session_id>/messages/",
        CommunicationsConversationMessagesView.as_view(),
    ),
    path(
        "conversations/<str:session_id>/mark-read/",
        CommunicationsConversationMarkReadView.as_view(),
    ),
    path("channels/", CommunicationsChannelsView.as_view()),
    path("whatsapp-logs/", CommunicationsWhatsappLogsView.as_view()),
]
