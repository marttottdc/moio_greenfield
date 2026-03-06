from django.urls import include, path

from crm.views import generic_webhook_receiver

urlpatterns = [
    path("api/v1/auth/", include("crm.api.auth.urls")),
    path("api/v1/settings/", include("crm.api.settings.urls")),
    path("api/v1/users/", include("portal.api.users.urls")),
    path("api/v1/public/", include("crm.api.public_urls")),
    path("api/v1/resources/", include("resources.api.urls")),
    path("webhooks/<str:webhook_id>/", generic_webhook_receiver, name="generic_webhook_receiver"),
]
