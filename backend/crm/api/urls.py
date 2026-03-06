from django.urls import include, path

urlpatterns = [
    path("contacts/", include("crm.api.contacts.urls")),
    path("communications/", include("crm.api.communications.urls")),
    path("tickets/", include("crm.api.tickets.urls")),
    path("deals/", include("crm.api.deals.urls")),
    path("templates/", include("crm.api.templates.urls")),
    path("dashboard/", include("crm.api.dashboard.urls")),
    path("knowledge/", include("crm.api.knowledge.urls")),
    path("customers/", include("crm.api.customers.urls")),
    path("tags/", include("crm.api.tags.urls")),
    path("activities/", include("crm.api.activities.urls")),
    path("activity_types/", include("crm.api.activity_types.urls")),
    path("products/", include("crm.api.products.urls")),
    path("contact_types/", include("crm.api.contact_types.urls")),
]
