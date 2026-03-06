from __future__ import annotations

"""moio_calendar.views – neat rebuild
-------------------------------------------------
• All CRUD via generic class‑based views (+ LoginRequired & Tenant mixins)
• Consistent tenant scoping through `TenantRequiredMixin`
• Single `to_json()` helper for CalendarEvent → FullCalendar
• POST‑only deletes (CSRF‑safe)
• If *djangorestframework* is present, an automatic `CalendarEventViewSet` is exposed
"""

from datetime import date
from typing import Any, Dict, List, Type

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db import models
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.urls import reverse, reverse_lazy
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from django.views import View
from django.views.decorators.http import require_POST
from django.views.generic import (
    CreateView,
    DeleteView,
    DetailView,
    ListView,
    TemplateView,
    UpdateView,
)

from moio_calendar.forms import (
    AvailabilitySlotForm,
    BookingTypeForm,
    CalendarEventForm,
    CalendarForm,
    SharedResourceForm,
)
from moio_calendar.models import (
    AvailabilitySlot,
    BookingType,
    Calendar,
    CalendarEvent,
    CalendarPermission,
    EventStatus,
    SharedResource,
)

# ---------------------------------------------------------------------------
# GENERIC CRUD helpers
# ---------------------------------------------------------------------------

class _BaseMsgMixin:
    success_message: str = "Saved."

    def form_valid(self, form):  # type: ignore[override]
        messages.success(self.request, _(self.success_message))
        return super().form_valid(form)


class _BaseDeleteMsgMixin:
    success_message: str = "Deleted."

    def delete(self, request, *args, **kwargs):  # type: ignore[override]
        messages.success(request, _(self.success_message))
        return super().delete(request, *args, **kwargs)


# ---------------------------------------------------------------------------
# Tenant mixin
# ---------------------------------------------------------------------------

class TenantRequiredMixin(LoginRequiredMixin):
    """Mixin that injects `self.tenant` and limits querysets."""

    tenant_attr: str = "tenant"

    def dispatch(self, request, *args, **kwargs):  # type: ignore[override]
        self.tenant = getattr(request, "tenant", request.user.tenant)  # type: ignore[attr-defined]
        return super().dispatch(request, *args, **kwargs)

    # queryset restriction ---------------------------------------------------
    def get_queryset(self):  # type: ignore[override]
        qs = super().get_queryset()  # type: ignore[misc]
        tenant_field = self.tenant_attr
        return qs.filter(**{tenant_field: self.tenant})

    # form injection ---------------------------------------------------------
    def form_valid(self, form):  # type: ignore[override]
        if hasattr(form.instance, self.tenant_attr):
            setattr(form.instance, self.tenant_attr, self.tenant)
        return super().form_valid(form)


class CalendarPermissionMixin:
    """Mixin to check calendar permissions for views."""

    def get_calendar(self, calendar_id):
        """Get calendar and check permissions."""
        try:
            calendar = Calendar.objects.get(id=calendar_id, tenant=self.tenant)
            if not calendar.can_view(self.request.user):
                from django.http import Http404
                raise Http404("Calendar not found or access denied")
            return calendar
        except Calendar.DoesNotExist:
            from django.http import Http404
            raise Http404("Calendar not found")

    def can_edit_calendar(self, calendar):
        """Check if user can edit the calendar."""
        return calendar.can_edit(self.request.user)


# ---------------------------------------------------------------------------
# GENERIC CRUD helpers
# ---------------------------------------------------------------------------

class _BaseMsgMixin:
    success_message: str = "Saved."

    def form_valid(self, form):  # type: ignore[override]
        messages.success(self.request, _(self.success_message))
        return super().form_valid(form)


class _BaseDeleteMsgMixin:
    success_message: str = "Deleted."

    def delete(self, request, *args, **kwargs):  # type: ignore[override]
        messages.success(request, _(self.success_message))
        return super().delete(request, *args, **kwargs)


# ---------------------------------------------------------------------------
# Helper serialiser
# ---------------------------------------------------------------------------

def event_to_json(event: CalendarEvent) -> Dict[str, Any]:
    return {
        "id": str(event.id),
        "title": event.title,
        "start": event.start_time.isoformat(),
        "end": event.end_time.isoformat(),
        "description": event.description,
        "location": event.location,
        "status": event.status,
        "type": event.event_type,
    }


# ---------------------------------------------------------------------------
# CALENDAR DASHBOARD
# ---------------------------------------------------------------------------

class CalendarView(TenantRequiredMixin, TemplateView):
    template_name = "calendar/calendar.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        today = timezone.localdate()
        ctx["initial_date"] = date(today.year, today.month, 1).isoformat()
        return ctx


class CalendarEventsJSON(TenantRequiredMixin, View):
    """Feed for FullCalendar."""

    def get(self, request, *args, **kwargs):  # type: ignore[override]
        # Get all calendars the user can view
        user_calendars = Calendar.objects.filter(
            models.Q(owner=request.user) |
            models.Q(visibility='public', tenant=self.tenant) |
            models.Q(visibility='team', tenant=self.tenant) |
            models.Q(visibility='shared', allowed_users=request.user)
        ).distinct()

        events = CalendarEvent.objects.filter(calendar__in=user_calendars)
        return JsonResponse([event_to_json(e) for e in events], safe=False)


# ---------------------------------------------------------------------------
# CALENDAR MANAGEMENT VIEWS
# ---------------------------------------------------------------------------

class CalendarListView(TenantRequiredMixin, ListView):
    model = Calendar
    template_name = "calendar/calendar_list.html"
    paginate_by = 20

    def get_queryset(self):  # type: ignore[override]
        return Calendar.objects.filter(
            models.Q(owner=self.request.user) |
            models.Q(visibility='public', tenant=self.tenant) |
            models.Q(visibility='team', tenant=self.tenant) |
            models.Q(visibility='shared', allowed_users=self.request.user)
        ).distinct().order_by('-is_default', 'name')


class CalendarCreateView(_BaseMsgMixin, TenantRequiredMixin, CreateView):
    model = Calendar
    form_class = CalendarForm
    template_name = "calendar/calendar_form.html"
    success_url = reverse_lazy("moio_calendar:calendar_list")
    success_message = "Calendar created successfully!"

    def form_valid(self, form):  # type: ignore[override]
        form.instance.owner = self.request.user
        # If this is the first calendar for the user, make it default
        if not Calendar.objects.filter(owner=self.request.user).exists():
            form.instance.is_default = True
        return super().form_valid(form)


class CalendarUpdateView(_BaseMsgMixin, TenantRequiredMixin, CalendarPermissionMixin, UpdateView):
    model = Calendar
    form_class = CalendarForm
    template_name = "calendar/calendar_form.html"
    success_url = reverse_lazy("moio_calendar:calendar_list")
    success_message = "Calendar updated successfully!"

    def get_object(self, queryset=None):  # type: ignore[override]
        calendar = super().get_object(queryset)
        if not self.can_edit_calendar(calendar):
            from django.http import Http404
            raise Http404("You don't have permission to edit this calendar")
        return calendar


class CalendarDeleteView(_BaseDeleteMsgMixin, TenantRequiredMixin, CalendarPermissionMixin, DeleteView):
    model = Calendar
    success_url = reverse_lazy("moio_calendar:calendar_list")
    success_message = "Calendar deleted successfully!"

    def get_object(self, queryset=None):  # type: ignore[override]
        calendar = super().get_object(queryset)
        if calendar.owner != self.request.user:
            from django.http import Http404
            raise Http404("You don't have permission to delete this calendar")
        return calendar


# ---------------------------------------------------------------------------
# EVENT VIEWS
# ---------------------------------------------------------------------------

class EventListView(TenantRequiredMixin, ListView):
    model = CalendarEvent
    paginate_by = 20
    ordering = "-start_time"
    template_name = "calendar/event_list.html"


class EventCreateView(_BaseMsgMixin, TenantRequiredMixin, CalendarPermissionMixin, CreateView):
    model = CalendarEvent
    form_class = CalendarEventForm
    template_name = "calendar/event_form.html"
    success_message = "Event created successfully!"
    success_url = reverse_lazy("moio_calendar:calendar")

    def get_form(self, form_class=None):  # type: ignore[override]
        form = super().get_form(form_class)
        form.fields['calendar'].queryset = Calendar.objects.filter(
            models.Q(owner=self.request.user) |
            models.Q(visibility='team', tenant=self.tenant) |
            models.Q(visibility='shared', allowed_users=self.request.user)
        ).distinct()
        return form

    def form_valid(self, form):  # type: ignore[override]
        form.instance.organizer = self.request.user
        # Check calendar permissions
        calendar = form.instance.calendar
        if not self.can_edit_calendar(calendar):
            from django.forms import ValidationError
            form.add_error('calendar', 'You do not have permission to create events in this calendar')
            return self.form_invalid(form)
        return super().form_valid(form)


class EventUpdateView(_BaseMsgMixin, TenantRequiredMixin, CalendarPermissionMixin, UpdateView):
    model = CalendarEvent
    form_class = CalendarEventForm
    template_name = "calendar/event_form.html"
    success_message = "Event updated successfully!"
    success_url = reverse_lazy("moio_calendar:calendar")

    def get_form(self, form_class=None):  # type: ignore[override]
        form = super().get_form(form_class)
        form.fields['calendar'].queryset = Calendar.objects.filter(
            models.Q(owner=self.request.user) |
            models.Q(visibility='team', tenant=self.tenant) |
            models.Q(visibility='shared', allowed_users=self.request.user)
        ).distinct()
        return form

    def get_object(self, queryset=None):  # type: ignore[override]
        event = super().get_object(queryset)
        if not self.can_edit_calendar(event.calendar):
            from django.http import Http404
            raise Http404("You don't have permission to edit events in this calendar")
        return event


class EventDeleteView(_BaseDeleteMsgMixin, TenantRequiredMixin, CalendarPermissionMixin, DeleteView):
    model = CalendarEvent
    success_url = reverse_lazy("moio_calendar:calendar")
    success_message = "Event deleted successfully!"

    def get_object(self, queryset=None):  # type: ignore[override]
        event = super().get_object(queryset)
        if not self.can_edit_calendar(event.calendar):
            from django.http import Http404
            raise Http404("You don't have permission to delete events in this calendar")
        return event


class EventDetailView(TenantRequiredMixin, DetailView):
    model = CalendarEvent
    template_name = "calendar/event_detail.html"


# ---------------------------------------------------------------------------
# AVAILABILITY VIEWS
# ---------------------------------------------------------------------------

class AvailabilityListView(TenantRequiredMixin, ListView):
    model = AvailabilitySlot
    template_name = "calendar/availability_list.html"

    def get_queryset(self):  # type: ignore[override]
        return (
            super()
            .get_queryset()
            .filter(calendar__owner=self.request.user)
            .order_by("day_of_week", "start_time")
        )


class AvailabilityCreateView(_BaseMsgMixin, TenantRequiredMixin, CreateView):
    model = AvailabilitySlot
    form_class = AvailabilitySlotForm
    template_name = "calendar/availability_form.html"
    success_url = reverse_lazy("moio_calendar:availability_list")
    success_message = "Availability slot created successfully!"

    def form_valid(self, form):  # type: ignore[override]
        calendar = Calendar.objects.filter(owner=self.request.user).order_by('-is_default', 'created_at').first()
        if calendar is None:
            form.add_error(None, "Create a calendar before adding availability slots.")
            return self.form_invalid(form)
        form.instance.calendar = calendar
        return super().form_valid(form)


class AvailabilityUpdateView(_BaseMsgMixin, TenantRequiredMixin, UpdateView):
    model = AvailabilitySlot
    form_class = AvailabilitySlotForm
    template_name = "calendar/availability_form.html"
    success_url = reverse_lazy("moio_calendar:availability_list")
    success_message = "Availability updated successfully!"


class AvailabilityDeleteView(_BaseDeleteMsgMixin, TenantRequiredMixin, DeleteView):
    model = AvailabilitySlot
    template_name = "calendar/availability_confirm_delete.html"
    success_url = reverse_lazy("moio_calendar:availability_list")
    success_message = "Availability slot deleted successfully!"


# ---------------------------------------------------------------------------
# SHARED RESOURCE VIEWS
# ---------------------------------------------------------------------------

class ResourceListView(TenantRequiredMixin, ListView):
    model = SharedResource
    template_name = "calendar/resource_list.html"

class ResourceCreateView(_BaseMsgMixin, TenantRequiredMixin, CreateView):
    model = SharedResource
    form_class = SharedResourceForm
    template_name = "calendar/resource_form.html"
    success_url = reverse_lazy("moio_calendar:resource_list")
    success_message = "Resource created successfully!"

class ResourceUpdateView(_BaseMsgMixin, TenantRequiredMixin, UpdateView):
    model = SharedResource
    form_class = SharedResourceForm
    template_name = "calendar/resource_form.html"
    success_url = reverse_lazy("moio_calendar:resource_list")
    success_message = "Resource updated successfully!"

class ResourceDeleteView(_BaseDeleteMsgMixin, TenantRequiredMixin, DeleteView):
    model = SharedResource
    template_name = "calendar/resource_confirm_delete.html"
    success_url = reverse_lazy("moio_calendar:resource_list")
    success_message = "Resource deleted successfully!"


# ---------------------------------------------------------------------------
# BOOKING TYPE VIEWS
# ---------------------------------------------------------------------------

class BookingTypeListView(TenantRequiredMixin, ListView):
    model = BookingType
    template_name = "calendar/booking_type_list.html"

    def get_queryset(self):  # type: ignore[override]
        return super().get_queryset().filter(calendar__owner=self.request.user)


class BookingTypeCreateView(_BaseMsgMixin, TenantRequiredMixin, CreateView):
    model = BookingType
    form_class = BookingTypeForm
    template_name = "calendar/booking_type_form.html"
    success_url = reverse_lazy("moio_calendar:booking_type_list")
    success_message = "Booking type created successfully!"

    def form_valid(self, form):  # type: ignore[override]
        calendar = Calendar.objects.filter(owner=self.request.user).order_by('-is_default', 'created_at').first()
        if calendar is None:
            form.add_error(None, "Create a calendar before creating booking types.")
            return self.form_invalid(form)
        form.instance.calendar = calendar
        return super().form_valid(form)


class BookingTypeUpdateView(_BaseMsgMixin, TenantRequiredMixin, UpdateView):
    model = BookingType
    form_class = BookingTypeForm
    template_name = "calendar/booking_type_form.html"
    success_url = reverse_lazy("moio_calendar:booking_type_list")
    success_message = "Booking type updated successfully!"


class BookingTypeDeleteView(_BaseDeleteMsgMixin, TenantRequiredMixin, DeleteView):
    model = BookingType
    template_name = "calendar/booking_type_confirm_delete.html"
    success_url = reverse_lazy("moio_calendar:booking_type_list")
    success_message = "Booking type deleted successfully!"


# ---------------------------------------------------------------------------
# API ENDPOINTS – plain JSON or DRF ViewSet
# ---------------------------------------------------------------------------

def api_events(request):  # pragma: no cover
    """Fallback JSON API if DRF not installed."""
    events = CalendarEvent.objects.filter(tenant=request.tenant)
    return JsonResponse([event_to_json(e) for e in events], safe=False)


# Optional DRF hook ----------------------------------------------------------
try:
    from .api import (
        CalendarViewSet, CalendarEventViewSet, AvailabilitySlotViewSet,
        SharedResourceViewSet, ResourceBookingViewSet, BookingTypeViewSet,
        EventAttendeeViewSet, public_booking_types, public_booking_availability,
        create_public_booking
    )
except ModuleNotFoundError:
    # API module not found; ignore.
    pass
