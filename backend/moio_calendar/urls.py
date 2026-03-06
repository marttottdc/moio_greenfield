# moio_calendar/urls.py
from django.urls import path, include
from . import views as views   # the rebuilt file
from .monitoring import health_check, metrics_endpoint

app_name = 'moio_calendar'

urlpatterns = [
    # ─── Calendar dashboard & feed ───────────────────────────────
    path("",              views.CalendarView.as_view(),         name="calendar"),
    path("feed.json",     views.CalendarEventsJSON.as_view(),   name="calendar-feed"),

    # ─── Calendar management ────────────────────────────────────
    path("calendars/",                    views.CalendarListView.as_view(),   name="calendar_list"),
    path("calendars/new/",                views.CalendarCreateView.as_view(), name="calendar_create"),
    path("calendars/<uuid:pk>/edit/",     views.CalendarUpdateView.as_view(), name="calendar_update"),
    path("calendars/<uuid:pk>/delete/",   views.CalendarDeleteView.as_view(), name="calendar_delete"),

    # ─── Calendar events CRUD ───────────────────────────────────
    path("events/",                       views.EventListView.as_view(),   name="event_list"),
    path("events/new/",                   views.EventCreateView.as_view(), name="event_create"),
    path("events/<uuid:pk>/",             views.EventDetailView.as_view(), name="event_detail"),
    path("events/<uuid:pk>/edit/",        views.EventUpdateView.as_view(), name="event_update"),
    path("events/<uuid:pk>/delete/",      views.EventDeleteView.as_view(), name="event_delete"),

    # ─── Availability slots ─────────────────────────────────────
    path("availability/",                       views.AvailabilityListView.as_view(),   name="availability_list"),
    path("availability/new/",                   views.AvailabilityCreateView.as_view(), name="availability_create"),
    path("availability/<uuid:pk>/edit/",        views.AvailabilityUpdateView.as_view(), name="availability_update"),
    path("availability/<uuid:pk>/delete/",      views.AvailabilityDeleteView.as_view(), name="availability_delete"),

    # ─── Shared resources ───────────────────────────────────────
    path("resources/",                       views.ResourceListView.as_view(),   name="resource_list"),
    path("resources/new/",                   views.ResourceCreateView.as_view(), name="resource_create"),
    path("resources/<uuid:pk>/edit/",        views.ResourceUpdateView.as_view(), name="resource_update"),
    path("resources/<uuid:pk>/delete/",      views.ResourceDeleteView.as_view(), name="resource_delete"),

    # ─── Booking types ──────────────────────────────────────────
    path("booking-types/",                       views.BookingTypeListView.as_view(),   name="booking_type_list"),
    path("booking-types/new/",                   views.BookingTypeCreateView.as_view(), name="booking_type_create"),
    path("booking-types/<uuid:pk>/edit/",        views.BookingTypeUpdateView.as_view(), name="booking_type_update"),
    path("booking-types/<uuid:pk>/delete/",      views.BookingTypeDeleteView.as_view(), name="booking_type_delete"),

    # ─── JSON fallback API (if DRF not installed) ───────────────
    path("api/events/", views.api_events, name="api_events"),

    # ─── Public Booking API (No Authentication) ─────────────────
    path("api/public/booking-types/", views.public_booking_types, name="public_booking_types"),
    path("api/public/availability/<slug:booking_slug>/", views.public_booking_availability, name="public_booking_availability"),
    path("api/public/book/", views.create_public_booking, name="create_public_booking"),

    # ─── Monitoring & Health Checks ─────────────────────────────
    path("health/", health_check, name="calendar_health_check"),
    path("metrics/", metrics_endpoint, name="calendar_metrics"),
]

# -----------------------------------------------------------------
# Optional: DRF router for all calendar API endpoints
# -----------------------------------------------------------------
try:
    from rest_framework.routers import DefaultRouter
    from .api import (
        CalendarViewSet, CalendarEventViewSet, AvailabilitySlotViewSet,
        SharedResourceViewSet, ResourceBookingViewSet, BookingTypeViewSet,
        EventAttendeeViewSet
    )

    router = DefaultRouter()
    router.register("api/calendars", CalendarViewSet, basename="api-calendars")
    router.register("api/events", CalendarEventViewSet, basename="api-events")
    router.register("api/availability", AvailabilitySlotViewSet, basename="api-availability")
    router.register("api/resources", SharedResourceViewSet, basename="api-resources")
    router.register("api/resource-bookings", ResourceBookingViewSet, basename="api-resource-bookings")
    router.register("api/booking-types", BookingTypeViewSet, basename="api-booking-types")
    router.register("api/attendees", EventAttendeeViewSet, basename="api-attendees")
    urlpatterns += [path("", include(router.urls))]
except ModuleNotFoundError:
    # DRF not installed → ignore
    pass