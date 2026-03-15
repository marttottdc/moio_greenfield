from django.urls import path

from crm.api.dashboard.views import DashboardSummaryView

urlpatterns = [
    path("summary/", DashboardSummaryView.as_view()),
]
