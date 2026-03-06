from django.urls import path
from portal.api.provisioning import SelfProvisionView

urlpatterns = [
    path("self-provision/", SelfProvisionView.as_view(), name="tenants-self-provision"),
]
