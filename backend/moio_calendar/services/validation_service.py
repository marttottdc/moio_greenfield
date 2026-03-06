"""
Business logic validation service for calendar operations.
Handles double-booking prevention, availability checks, and business rule enforcement.
"""

from datetime import datetime, timedelta
from typing import List, Dict, Optional, Tuple
from django.db import models
from django.utils import timezone
from django.core.exceptions import ValidationError

from ..models import (
    Calendar, CalendarEvent, AvailabilitySlot, SharedResource,
    ResourceBooking, BookingType, CalendarVisibility, EventStatus
)


class CalendarValidationError(ValidationError):
    """Custom validation error for calendar operations."""
    pass


class CalendarValidationService:
    """Service for validating calendar business logic."""

    @staticmethod
    def validate_event_creation(
        calendar: Calendar,
        start_time: datetime,
        end_time: datetime,
        exclude_event_id: Optional[str] = None,
        user=None
    ) -> None:
        """
        Validate event creation/update for business rules.

        Args:
            calendar: Calendar instance
            start_time: Event start time
            end_time: Event end time
            exclude_event_id: Event ID to exclude from conflict check (for updates)
            user: User performing the action

        Raises:
            CalendarValidationError: If validation fails
        """
        # Check calendar permissions
        if user and not calendar.can_edit(user):
            raise CalendarValidationError("You do not have permission to create events in this calendar")

        # Validate time ordering
        if start_time >= end_time:
            raise CalendarValidationError("Event end time must be after start time")

        # Check for time conflicts
        conflicts = CalendarEvent.objects.filter(
            calendar=calendar,
            start_time__lt=end_time,
            end_time__gt=start_time,
        ).exclude(status=EventStatus.CANCELLED)

        if exclude_event_id:
            conflicts = conflicts.exclude(id=exclude_event_id)

        if conflicts.exists():
            conflict_events = list(conflicts.values_list('title', 'start_time', 'end_time')[:3])
            conflict_details = [
                f"'{title}' ({start.strftime('%H:%M')}-{end.strftime('%H:%M')})"
                for title, start, end in conflict_events
            ]
            raise CalendarValidationError(
                f"Time conflict with existing events: {', '.join(conflict_details)}"
            )

    @staticmethod
    def validate_resource_booking(
        resource: SharedResource,
        start_time: datetime,
        end_time: datetime,
        exclude_booking_id: Optional[str] = None,
        user=None
    ) -> None:
        """
        Validate resource booking for availability and permissions.

        Args:
            resource: SharedResource instance
            start_time: Booking start time
            end_time: Booking end time
            exclude_booking_id: Booking ID to exclude from conflict check
            user: User making the booking

        Raises:
            CalendarValidationError: If validation fails
        """
        # Check resource permissions
        if user and not resource.calendar.can_edit(user):
            raise CalendarValidationError("You do not have permission to book this resource")

        # Check if resource is active
        if not resource.is_active:
            raise CalendarValidationError("This resource is not available for booking")

        # Validate time ordering
        if start_time >= end_time:
            raise CalendarValidationError("Booking end time must be after start time")

        # Check duration constraints
        booking_duration = end_time - start_time
        if booking_duration < resource.min_booking_duration:
            raise CalendarValidationError(
                f"Minimum booking duration is {resource.min_booking_duration}"
            )
        if booking_duration > resource.max_booking_duration:
            raise CalendarValidationError(
                f"Maximum booking duration is {resource.max_booking_duration}"
            )

        # Check advance booking limit
        now = timezone.now()
        max_advance = now + timedelta(days=resource.advance_booking_days)
        if start_time > max_advance:
            raise CalendarValidationError(
                f"Cannot book more than {resource.advance_booking_days} days in advance"
            )

        # Check for booking conflicts
        conflicts = ResourceBooking.objects.filter(
            resource=resource,
            start_time__lt=end_time,
            end_time__gt=start_time,
            status__in=['pending', 'confirmed']
        )

        if exclude_booking_id:
            conflicts = conflicts.exclude(id=exclude_booking_id)

        if conflicts.exists():
            conflict_details = []
            for booking in conflicts[:3]:
                user_name = booking.booked_by.get_full_name() or booking.booked_by.username
                conflict_details.append(
                    f"{user_name} ({booking.start_time.strftime('%H:%M')}-{booking.end_time.strftime('%H:%M')})"
                )

            raise CalendarValidationError(
                f"Resource is already booked: {', '.join(conflict_details)}"
            )

    @staticmethod
    def validate_availability_slot(
        calendar: Calendar,
        day_of_week: int,
        start_time: str,
        end_time: str,
        slot_duration: timedelta,
        user=None
    ) -> None:
        """
        Validate availability slot configuration.

        Args:
            calendar: Calendar instance
            day_of_week: Day of week (0-6)
            start_time: Start time string (HH:MM:SS)
            end_time: End time string (HH:MM:SS)
            slot_duration: Duration of each slot
            user: User creating the slot

        Raises:
            CalendarValidationError: If validation fails
        """
        # Check permissions
        if user and not calendar.can_edit(user):
            raise CalendarValidationError("You do not have permission to manage availability for this calendar")

        # Validate day of week
        if not (0 <= day_of_week <= 6):
            raise CalendarValidationError("Day of week must be between 0 (Monday) and 6 (Sunday)")

        start_time_obj = datetime.strptime(start_time, '%H:%M:%S').time()
        end_time_obj = datetime.strptime(end_time, '%H:%M:%S').time()

        # Validate time ordering
        if start_time_obj >= end_time_obj:
            raise CalendarValidationError("End time must be after start time")

        # Validate slot duration is reasonable
        total_available = datetime.combine(datetime.min, end_time_obj) - datetime.combine(datetime.min, start_time_obj)
        total_available_seconds = total_available.total_seconds()

        if slot_duration.total_seconds() <= 0:
            raise CalendarValidationError("Slot duration must be positive")

        if slot_duration.total_seconds() > total_available_seconds:
            raise CalendarValidationError("Slot duration cannot exceed available time")

        # Check for overlapping slots on same day
        existing_slots = AvailabilitySlot.objects.filter(
            calendar=calendar,
            day_of_week=day_of_week,
            is_active=True
        )

        for slot in existing_slots:
            # Check for time overlap
            if (start_time_obj < slot.end_time and end_time_obj > slot.start_time):
                raise CalendarValidationError(
                    f"Time overlap with existing availability slot ({slot.start_time}-{slot.end_time})"
                )

    @staticmethod
    def validate_booking_type(
        calendar: Calendar,
        booking_slug: str,
        duration: timedelta,
        user=None
    ) -> None:
        """
        Validate booking type configuration.

        Args:
            calendar: Calendar instance
            booking_slug: Unique slug for public booking
            duration: Booking duration
            user: User creating the booking type

        Raises:
            CalendarValidationError: If validation fails
        """
        # Check permissions
        if user and not calendar.can_edit(user):
            raise CalendarValidationError("You do not have permission to manage booking types for this calendar")

        # Validate booking slug uniqueness
        if BookingType.objects.filter(booking_slug=booking_slug).exclude(calendar=calendar).exists():
            raise CalendarValidationError("Booking slug must be unique across all calendars")

        # Validate duration is reasonable
        if duration.total_seconds() <= 0:
            raise CalendarValidationError("Booking duration must be positive")

        if duration.total_seconds() > 8 * 3600:  # 8 hours max
            raise CalendarValidationError("Booking duration cannot exceed 8 hours")

    @staticmethod
    def get_available_slots(
        calendar: Calendar,
        booking_type: BookingType,
        start_date: datetime.date,
        end_date: datetime.date
    ) -> List[Dict]:
        """
        Get available time slots for a calendar and booking type.

        Args:
            calendar: Calendar instance
            booking_type: BookingType instance
            start_date: Start date for availability check
            end_date: End date for availability check

        Returns:
            List of available slot dictionaries
        """
        available_slots = []

        # Get availability slots for the calendar
        availability_slots = AvailabilitySlot.objects.filter(
            calendar=calendar,
            is_active=True
        )
        range_start = timezone.make_aware(datetime.combine(start_date, datetime.min.time()))
        range_end = timezone.make_aware(datetime.combine(end_date + timedelta(days=1), datetime.min.time()))

        events = CalendarEvent.objects.filter(
            calendar=calendar,
            start_time__lt=range_end,
            end_time__gt=range_start,
        ).exclude(status=EventStatus.CANCELLED).only('start_time', 'end_time')

        events_by_date: Dict[datetime.date, List[Tuple[datetime, datetime]]] = {}
        for event in events:
            event_date = timezone.localtime(event.start_time).date()
            event_end_date = timezone.localtime(event.end_time).date()

            while event_date <= event_end_date:
                events_by_date.setdefault(event_date, []).append((event.start_time, event.end_time))
                event_date += timedelta(days=1)

        current_date = start_date
        while current_date <= end_date:
            # Find availability for this day
            day_availability = availability_slots.filter(day_of_week=current_date.weekday())

            for availability in day_availability:
                day_events = events_by_date.get(current_date, [])
                # Generate time slots within availability window
                slot_time = datetime.combine(current_date, availability.start_time)
                slot_time = timezone.make_aware(slot_time)

                end_slot_time = datetime.combine(current_date, availability.end_time)
                end_slot_time = timezone.make_aware(end_slot_time)

                current_slot = slot_time
                while current_slot + booking_type.duration <= end_slot_time:
                    slot_end = current_slot + booking_type.duration

                    has_conflict = any(
                        event_start < slot_end and event_end > current_slot
                        for event_start, event_end in day_events
                    )

                    if not has_conflict:
                        available_slots.append({
                            'datetime': current_slot.isoformat(),
                            'date': current_date.isoformat(),
                            'start_time': current_slot.strftime('%H:%M'),
                            'end_time': slot_end.strftime('%H:%M'),
                            'display_date': current_slot.strftime('%A, %B %d, %Y'),
                            'display_time': current_slot.strftime('%I:%M %p'),
                        })

                    current_slot += availability.slot_duration

            current_date += timedelta(days=1)

        return available_slots

    @staticmethod
    def validate_public_booking(
        booking_slug: str,
        selected_datetime: datetime,
        lock_calendar: bool = False
    ) -> Tuple[BookingType, Calendar]:
        """
        Validate public booking request.

        Args:
            booking_slug: Booking type slug
            selected_datetime: Requested booking time

        Returns:
            Tuple of (BookingType, Calendar)

        Raises:
            CalendarValidationError: If validation fails
        """
        # Get booking type
        try:
            booking_type = BookingType.objects.select_related('calendar').get(
                booking_slug=booking_slug,
                is_active=True,
                calendar__visibility=CalendarVisibility.PUBLIC
            )
        except BookingType.DoesNotExist:
            raise CalendarValidationError("Booking type not found or not available")

        if lock_calendar:
            booking_type.calendar = Calendar.objects.select_for_update().get(id=booking_type.calendar_id)

        # Check if booking is in the future
        if selected_datetime <= timezone.now():
            raise CalendarValidationError("Cannot book appointments in the past")

        # Check advance booking limit
        max_advance = timezone.now() + timedelta(days=booking_type.advance_booking_days)
        if selected_datetime > max_advance:
            raise CalendarValidationError(
                f"Cannot book more than {booking_type.advance_booking_days} days in advance"
            )

        # Calculate end time
        end_datetime = selected_datetime + booking_type.duration

        # Check for conflicts
        conflicts = CalendarEvent.objects.filter(
            calendar=booking_type.calendar,
            start_time__lt=end_datetime,
            end_time__gt=selected_datetime,
        ).exclude(status=EventStatus.CANCELLED)

        if conflicts.exists():
            raise CalendarValidationError("Selected time slot is no longer available")

        return booking_type, booking_type.calendar

    @staticmethod
    def validate_calendar_sharing(
        calendar: Calendar,
        target_user,
        can_edit: bool,
        requesting_user
    ) -> None:
        """
        Validate calendar sharing permissions.

        Args:
            calendar: Calendar to share
            target_user: User to share with
            can_edit: Whether to grant edit permissions
            requesting_user: User making the request

        Raises:
            CalendarValidationError: If validation fails
        """
        if calendar.owner != requesting_user:
            raise CalendarValidationError("Only calendar owner can manage sharing")

        if target_user == requesting_user:
            raise CalendarValidationError("Cannot share calendar with yourself")

        if calendar.visibility == CalendarVisibility.PRIVATE and not can_edit:
            raise CalendarValidationError("Private calendars can only be shared with edit permissions")

    @staticmethod
    def validate_calendar_creation(
        owner,
        name: str,
        visibility: str
    ) -> None:
        """
        Validate calendar creation.

        Args:
            owner: Calendar owner
            name: Calendar name
            visibility: Calendar visibility

        Raises:
            CalendarValidationError: If validation fails
        """
        if not name or not name.strip():
            raise CalendarValidationError("Calendar name is required")

        if visibility not in dict(CalendarVisibility.choices):
            raise CalendarValidationError("Invalid visibility setting")

        # Check name uniqueness for user
        if Calendar.objects.filter(owner=owner, name=name.strip()).exists():
            raise CalendarValidationError("Calendar name must be unique for this user")