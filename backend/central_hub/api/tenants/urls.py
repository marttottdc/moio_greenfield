from django.urls import path
from central_hub.api.provisioning import SelfProvisionView, ProvisionStatusView

urlpatterns = [
    path("self-provision/", SelfProvisionView.as_view(), name="tenants-self-provision"),
    path("provision-status/<str:task_id>/", ProvisionStatusView.as_view(), name="tenants-provision-status"),
]
