
from django.contrib import admin
from moio_calendar.models import (
    Calendar, CalendarPermission, CalendarEvent, EventAttendee,
    AvailabilitySlot, SharedResource, ResourceBooking, BookingType
)


@admin.register(Calendar)
class CalendarAdmin(admin.ModelAdmin):
    list_display = ('name', 'owner', 'visibility', 'is_default', 'tenant')
    list_filter = ('visibility', 'is_default', 'tenant', 'created_at')
    search_fields = ('name', 'description', 'owner__username')
    raw_id_fields = ('owner', 'tenant', 'allowed_users')


@admin.register(CalendarPermission)
class CalendarPermissionAdmin(admin.ModelAdmin):
    list_display = ('calendar', 'user', 'can_edit', 'added_at')
    list_filter = ('can_edit', 'added_at')
    raw_id_fields = ('calendar', 'user')


@admin.register(CalendarEvent)
class CalendarEventAdmin(admin.ModelAdmin):
    list_display = ('title', 'calendar', 'organizer', 'start_time', 'end_time', 'status', 'event_type')
    list_filter = ('status', 'event_type', 'calendar__visibility', 'tenant', 'created_at')
    search_fields = ('title', 'description', 'organizer__username', 'calendar__name')
    date_hierarchy = 'start_time'
    raw_id_fields = ('calendar', 'organizer', 'tenant')


@admin.register(EventAttendee)
class EventAttendeeAdmin(admin.ModelAdmin):
    list_display = ('event', 'user', 'status', 'added_at')
    list_filter = ('status', 'added_at')
    raw_id_fields = ('event', 'user')


@admin.register(AvailabilitySlot)
class AvailabilitySlotAdmin(admin.ModelAdmin):
    list_display = ('calendar', 'day_of_week', 'start_time', 'end_time', 'slot_duration', 'is_active')
    list_filter = ('day_of_week', 'is_active', 'tenant')
    raw_id_fields = ('calendar', 'tenant')


@admin.register(SharedResource)
class SharedResourceAdmin(admin.ModelAdmin):
    list_display = ('name', 'resource_type', 'capacity', 'location', 'is_active')
    list_filter = ('resource_type', 'is_active', 'tenant')
    search_fields = ('name', 'description', 'location')
    raw_id_fields = ('tenant',)


@admin.register(ResourceBooking)
class ResourceBookingAdmin(admin.ModelAdmin):
    list_display = ('resource', 'event', 'start_time', 'end_time', 'booked_by', 'status')
    list_filter = ('status', 'tenant', 'created_at')
    date_hierarchy = 'start_time'
    raw_id_fields = ('resource', 'event', 'booked_by', 'tenant')


@admin.register(BookingType)
class BookingTypeAdmin(admin.ModelAdmin):
    list_display = ('name', 'calendar', 'duration', 'booking_slug', 'is_active')
    list_filter = ('is_active', 'tenant', 'created_at')
    search_fields = ('name', 'description', 'booking_slug')
    prepopulated_fields = {'booking_slug': ('name',)}
    raw_id_fields = ('calendar', 'tenant')
