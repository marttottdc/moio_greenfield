from django.urls import include, path

urlpatterns = [
    path("", include("crm.api.urls")),
]

