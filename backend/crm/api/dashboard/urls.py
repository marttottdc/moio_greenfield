from django.urls import path

from crm.api.public_views import DashboardSummaryView

urlpatterns = [
    path("summary/", DashboardSummaryView.as_view()),
]
