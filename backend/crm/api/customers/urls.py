from django.urls import path

from crm.api.customers.views import CustomersView, CustomerDetailView

urlpatterns = [
    path("", CustomersView.as_view()),
    path("<uuid:customer_id>/", CustomerDetailView.as_view()),
]
