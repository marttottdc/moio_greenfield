from django.urls import path, re_path

from central_hub.integrations.v1.views.email import (
    EmailAccountsView,
    EmailAccountDetailView,
    EmailAccountEnableView,
    EmailAccountDisableView,
    EmailOAuthStartView,
    EmailOAuthCallbackView,
    EmailImapConnectView,
    EmailFlowAccountsView,
    EmailAccountHealthView,
    EmailMessagesListView,
    EmailMessageDetailView,
    EmailSendView,
)
from central_hub.integrations.v1.views.calendar import (
    CalendarAccountsView,
    CalendarAccountDetailView,
    CalendarFlowAccountsView,
    CalendarAccountHealthView,
    CalendarEventsListView,
    CalendarEventDetailView,
)

urlpatterns = [
    # Email (allow with or without trailing slash)
    re_path(r"^email/accounts/?$", EmailAccountsView.as_view(), name="integrations_email_accounts"),
    re_path(r"^email/accounts/(?P<pk>[0-9a-f-]+)/?$", EmailAccountDetailView.as_view(), name="integrations_email_account_detail"),
    re_path(r"^email/accounts/(?P<pk>[0-9a-f-]+)/enable/?$", EmailAccountEnableView.as_view(), name="integrations_email_account_enable"),
    re_path(r"^email/accounts/(?P<pk>[0-9a-f-]+)/disable/?$", EmailAccountDisableView.as_view(), name="integrations_email_account_disable"),
    re_path(r"^email/oauth/start/?$", EmailOAuthStartView.as_view(), name="integrations_email_oauth_start"),
    re_path(r"^email/oauth/callback/(?P<provider>[^/]+)/?$", EmailOAuthCallbackView.as_view(), name="integrations_email_oauth_callback"),
    re_path(r"^email/imap/connect/?$", EmailImapConnectView.as_view(), name="integrations_email_imap_connect"),
    re_path(r"^email/flow/accounts/?$", EmailFlowAccountsView.as_view(), name="integrations_email_flow_accounts"),
    re_path(r"^email/accounts/(?P<pk>[0-9a-f-]+)/health/?$", EmailAccountHealthView.as_view(), name="integrations_email_account_health"),
    re_path(r"^email/accounts/(?P<pk>[0-9a-f-]+)/messages/?$", EmailMessagesListView.as_view(), name="integrations_email_messages"),
    re_path(r"^email/accounts/(?P<pk>[0-9a-f-]+)/messages/(?P<message_id>[^/]+)/?$", EmailMessageDetailView.as_view(), name="integrations_email_message_detail"),
    re_path(r"^email/accounts/(?P<pk>[0-9a-f-]+)/send/?$", EmailSendView.as_view(), name="integrations_email_send"),

    # Calendar (allow with or without trailing slash)
    re_path(r"^calendar/accounts/?$", CalendarAccountsView.as_view(), name="integrations_calendar_accounts"),
    re_path(r"^calendar/accounts/(?P<pk>[0-9a-f-]+)/?$", CalendarAccountDetailView.as_view(), name="integrations_calendar_account_detail"),
    re_path(r"^calendar/flow/accounts/?$", CalendarFlowAccountsView.as_view(), name="integrations_calendar_flow_accounts"),
    re_path(r"^calendar/accounts/(?P<pk>[0-9a-f-]+)/health/?$", CalendarAccountHealthView.as_view(), name="integrations_calendar_account_health"),
    re_path(r"^calendar/accounts/(?P<pk>[0-9a-f-]+)/events/?$", CalendarEventsListView.as_view(), name="integrations_calendar_events"),
    re_path(r"^calendar/accounts/(?P<pk>[0-9a-f-]+)/events/(?P<event_id>[^/]+)/?$", CalendarEventDetailView.as_view(), name="integrations_calendar_event_detail"),
]

