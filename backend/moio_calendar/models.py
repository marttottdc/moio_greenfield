
import uuid
from django.db import models
from django.contrib.auth import get_user_model
from portal.models import Tenant

User = get_user_model()


class CalendarVisibility(models.TextChoices):
    PRIVATE = 'private', 'Private'
    SHARED = 'shared', 'Shared with specific users'
    TEAM = 'team', 'Team calendar'
    PUBLIC = 'public', 'Public calendar'


class Calendar(models.Model):
    """Individual user calendars and shared team calendars"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)

    # Ownership and permissions
    owner = models.ForeignKey(User, on_delete=models.CASCADE, related_name='owned_calendars')
    visibility = models.CharField(
        max_length=20,
        choices=CalendarVisibility.choices,
        default=CalendarVisibility.PRIVATE
    )
    allowed_users = models.ManyToManyField(
        User,
        through='CalendarPermission',
        related_name='shared_calendars',
        blank=True
    )

    # Appearance
    color = models.CharField(max_length=7, default='#3788d8')  # Hex color code
    is_default = models.BooleanField(default=False)  # One default calendar per user

    # Metadata
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['owner'],
                condition=models.Q(is_default=True),
                name='unique_default_calendar_per_owner'
            )
        ]
        ordering = ['-is_default', 'name']

    def __str__(self):
        return f"{self.name} ({self.owner.username})"

    def can_view(self, user):
        """Check if user can view this calendar"""
        if self.owner == user:
            return True
        if self.visibility == CalendarVisibility.PUBLIC:
            return True
        if self.visibility == CalendarVisibility.TEAM:
            # Check if user is in same tenant (team member)
            return user.tenant == self.tenant
        if self.visibility == CalendarVisibility.SHARED:
            return self.allowed_users.filter(id=user.id).exists()
        return False

    def can_edit(self, user):
        """Check if user can edit events in this calendar"""
        if self.owner == user:
            return True
        if self.visibility == CalendarVisibility.TEAM:
            return user.tenant == self.tenant
        if self.visibility == CalendarVisibility.SHARED:
            return CalendarPermission.objects.filter(
                calendar=self,
                user=user,
                can_edit=True
            ).exists()
        return False


class CalendarPermission(models.Model):
    """Permissions for shared calendars"""
    calendar = models.ForeignKey(Calendar, on_delete=models.CASCADE)
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    can_edit = models.BooleanField(default=False)  # View-only vs edit permissions
    added_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ['calendar', 'user']

    def __str__(self):
        return f"{self.user.username} - {self.calendar.name} ({'edit' if self.can_edit else 'view'})"


class EventStatus(models.TextChoices):
    SCHEDULED = 'scheduled', 'Scheduled'
    CONFIRMED = 'confirmed', 'Confirmed'
    CANCELLED = 'cancelled', 'Cancelled'
    COMPLETED = 'completed', 'Completed'


class EventType(models.TextChoices):
    MEETING = 'meeting', 'Meeting'
    APPOINTMENT = 'appointment', 'Appointment'
    CALL = 'call', 'Call'
    CONSULTATION = 'consultation', 'Consultation'
    OTHER = 'other', 'Other'


class CalendarEvent(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    start_time = models.DateTimeField()
    end_time = models.DateTimeField()
    event_type = models.CharField(max_length=20, choices=EventType.choices, default=EventType.MEETING)
    status = models.CharField(max_length=20, choices=EventStatus.choices, default=EventStatus.SCHEDULED)

    # Calendar association
    calendar = models.ForeignKey(Calendar, on_delete=models.CASCADE, related_name='events')

    # Participants
    organizer = models.ForeignKey(User, on_delete=models.CASCADE, related_name='organized_events')
    attendees = models.ManyToManyField(User, through='EventAttendee', related_name='calendar_events')

    # External attendee info
    external_attendee_name = models.CharField(max_length=100, blank=True)
    external_attendee_email = models.EmailField(blank=True)
    external_attendee_phone = models.CharField(max_length=20, blank=True)

    # Location/Meeting info
    location = models.CharField(max_length=200, blank=True)
    meeting_link = models.URLField(blank=True)

    # Metadata
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # Scheduling
    is_public = models.BooleanField(default=False)  # Can be booked by external users
    booking_link = models.CharField(max_length=100, unique=True, blank=True)
    
    class Meta:
        ordering = ['start_time']
    
    def __str__(self):
        return f"{self.title} - {self.start_time.strftime('%Y-%m-%d %H:%M')}"


class EventAttendee(models.Model):
    event = models.ForeignKey(CalendarEvent, on_delete=models.CASCADE)
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    status = models.CharField(max_length=20, choices=[
        ('pending', 'Pending'),
        ('accepted', 'Accepted'),
        ('declined', 'Declined'),
        ('maybe', 'Maybe')
    ], default='pending')
    added_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        unique_together = ['event', 'user']


class AvailabilitySlot(models.Model):
    """Define when a user is available for bookings"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    calendar = models.ForeignKey(Calendar, on_delete=models.CASCADE, related_name='availability_slots', null=True, blank=True)

    # Day of week (0=Monday, 6=Sunday)
    day_of_week = models.IntegerField(choices=[
        (0, 'Monday'), (1, 'Tuesday'), (2, 'Wednesday'), (3, 'Thursday'),
        (4, 'Friday'), (5, 'Saturday'), (6, 'Sunday')
    ])

    start_time = models.TimeField()
    end_time = models.TimeField()

    # Duration for bookable slots within this availability
    slot_duration = models.DurationField(help_text="Duration of each bookable slot")

    # Metadata
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        unique_together = ['calendar', 'day_of_week', 'start_time', 'end_time']
    
    def __str__(self):
        day_name = dict(self._meta.get_field('day_of_week').choices)[self.day_of_week]
        return f"{self.calendar.name} - {day_name} {self.start_time}-{self.end_time}"


class SharedResource(models.Model):
    """Shared resources that can be booked (meeting rooms, equipment, etc.)"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    calendar = models.ForeignKey(Calendar, on_delete=models.CASCADE, related_name='resources', null=True, blank=True)
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    resource_type = models.CharField(max_length=50, choices=[
        ('room', 'Meeting Room'),
        ('equipment', 'Equipment'),
        ('vehicle', 'Vehicle'),
        ('other', 'Other')
    ])

    # Capacity and constraints
    capacity = models.IntegerField(default=1)
    location = models.CharField(max_length=200, blank=True)

    # Booking settings
    advance_booking_days = models.IntegerField(default=30)
    min_booking_duration = models.DurationField(default='00:30:00')
    max_booking_duration = models.DurationField(default='04:00:00')

    # Metadata
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
        return f"{self.name} ({self.resource_type})"


class ResourceBooking(models.Model):
    """Bookings for shared resources"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    calendar = models.ForeignKey(Calendar, on_delete=models.CASCADE, related_name='resource_bookings', null=True, blank=True)
    resource = models.ForeignKey(SharedResource, on_delete=models.CASCADE, related_name='bookings')
    event = models.ForeignKey(CalendarEvent, on_delete=models.CASCADE, related_name='resource_bookings')

    # Booking details
    start_time = models.DateTimeField()
    end_time = models.DateTimeField()
    booked_by = models.ForeignKey(User, on_delete=models.CASCADE)

    # Status
    status = models.CharField(max_length=20, choices=[
        ('pending', 'Pending'),
        ('confirmed', 'Confirmed'),
        ('cancelled', 'Cancelled')
    ], default='pending')

    # Metadata
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['start_time']
    
    def __str__(self):
        return f"{self.resource.name} - {self.start_time.strftime('%Y-%m-%d %H:%M')}"


class BookingType(models.Model):
    """Predefined booking types (like Calendly event types)"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    calendar = models.ForeignKey(Calendar, on_delete=models.CASCADE, related_name='booking_types', null=True, blank=True)
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    duration = models.DurationField()

    # Booking settings
    buffer_time_before = models.DurationField(default='00:00:00')
    buffer_time_after = models.DurationField(default='00:00:00')
    advance_booking_days = models.IntegerField(default=30)

    # Public booking link
    booking_slug = models.SlugField(unique=True)
    is_active = models.BooleanField(default=True)

    # Metadata
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
        return f"{self.name} ({self.duration})"
