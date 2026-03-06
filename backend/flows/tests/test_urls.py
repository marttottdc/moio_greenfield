from django.urls import include, path

urlpatterns = [
    path("", include("flows.urls", namespace="flows")),
]
