from django.urls import path

urlpatterns = [
    path("__tenant-tests__/", lambda request: None, name="tenant_tests_noop"),
]
