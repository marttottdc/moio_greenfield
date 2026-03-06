"""
Tests for moio_calendar app.
"""

import pytest
from django.test import TestCase, Client
from django.contrib.auth import get_user_model
from django.utils import timezone
from datetime import datetime, timedelta
from rest_framework.test import APITestCase
from rest_framework import status
from django.urls import reverse

from .models import (
    Calendar, CalendarEvent, AvailabilitySlot, SharedResource,
    ResourceBooking, BookingType, CalendarVisibility, EventStatus
)
from .services.validation_service import CalendarValidationService, CalendarValidationError

User = get_user_model()


class CalendarModelTest(TestCase):
    """Test Calendar model functionality."""

    def setUp(self):
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123'
        )
        self.tenant = self.user.tenant

    def test_calendar_creation(self):
        """Test basic calendar creation."""
        calendar = Calendar.objects.create(
            name='Test Calendar',
            description='A test calendar',
            owner=self.user,
            tenant=self.tenant,
            visibility=CalendarVisibility.PRIVATE
        )

        self.assertEqual(calendar.name, 'Test Calendar')
        self.assertEqual(calendar.owner, self.user)
        self.assertTrue(calendar.can_view(self.user))
        self.assertTrue(calendar.can_edit(self.user))

    def test_default_calendar_creation(self):
        """Test that first calendar becomes default."""
        calendar = Calendar.objects.create(
            name='First Calendar',
            owner=self.user,
            tenant=self.tenant
        )

        self.assertTrue(calendar.is_default)

        # Second calendar should not be default
        calendar2 = Calendar.objects.create(
            name='Second Calendar',
            owner=self.user,
            tenant=self.tenant
        )

        self.assertFalse(calendar2.is_default)

    def test_calendar_permissions(self):
        """Test calendar sharing and permissions."""
        calendar = Calendar.objects.create(
            name='Shared Calendar',
            owner=self.user,
            tenant=self.tenant,
            visibility=CalendarVisibility.SHARED
        )

        other_user = User.objects.create_user(
            username='otheruser',
            email='other@example.com',
            password='testpass123'
        )

        # Initially, other user cannot view
        self.assertFalse(calendar.can_view(other_user))

        # Share calendar with view permissions
        from .models import CalendarPermission
        CalendarPermission.objects.create(
            calendar=calendar,
            user=other_user,
            can_edit=False
        )

        # Now other user can view but not edit
        self.assertTrue(calendar.can_view(other_user))
        self.assertFalse(calendar.can_edit(other_user))


class CalendarEventModelTest(TestCase):
    """Test CalendarEvent model functionality."""

    def setUp(self):
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123'
        )
        self.tenant = self.user.tenant
        self.calendar = Calendar.objects.create(
            name='Test Calendar',
            owner=self.user,
            tenant=self.tenant
        )

    def test_event_creation(self):
        """Test basic event creation."""
        start_time = timezone.now()
        end_time = start_time + timedelta(hours=1)

        event = CalendarEvent.objects.create(
            calendar=self.calendar,
            title='Test Event',
            description='A test event',
            start_time=start_time,
            end_time=end_time,
            organizer=self.user,
            tenant=self.tenant
        )

        self.assertEqual(event.title, 'Test Event')
        self.assertEqual(event.calendar, self.calendar)
        self.assertEqual(event.organizer, self.user)


class AvailabilitySlotModelTest(TestCase):
    """Test AvailabilitySlot model functionality."""

    def setUp(self):
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123'
        )
        self.tenant = self.user.tenant
        self.calendar = Calendar.objects.create(
            name='Test Calendar',
            owner=self.user,
            tenant=self.tenant
        )

    def test_availability_slot_creation(self):
        """Test availability slot creation."""
        slot = AvailabilitySlot.objects.create(
            calendar=self.calendar,
            day_of_week=0,  # Monday
            start_time='09:00:00',
            end_time='17:00:00',
            slot_duration=timedelta(minutes=30),
            tenant=self.tenant
        )

        self.assertEqual(slot.calendar, self.calendar)
        self.assertEqual(slot.day_of_week, 0)
        self.assertEqual(str(slot.start_time), '09:00:00')


class SharedResourceModelTest(TestCase):
    """Test SharedResource model functionality."""

    def setUp(self):
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123'
        )
        self.tenant = self.user.tenant
        self.calendar = Calendar.objects.create(
            name='Test Calendar',
            owner=self.user,
            tenant=self.tenant
        )

    def test_resource_creation(self):
        """Test shared resource creation."""
        resource = SharedResource.objects.create(
            calendar=self.calendar,
            name='Meeting Room A',
            description='Main conference room',
            resource_type='room',
            capacity=10,
            tenant=self.tenant
        )

        self.assertEqual(resource.name, 'Meeting Room A')
        self.assertEqual(resource.calendar, self.calendar)
        self.assertEqual(resource.capacity, 10)


class ResourceBookingModelTest(TestCase):
    """Test ResourceBooking model functionality."""

    def setUp(self):
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123'
        )
        self.tenant = self.user.tenant
        self.calendar = Calendar.objects.create(
            name='Test Calendar',
            owner=self.user,
            tenant=self.tenant
        )
        self.resource = SharedResource.objects.create(
            calendar=self.calendar,
            name='Meeting Room A',
            resource_type='room',
            capacity=10,
            tenant=self.tenant
        )

    def test_resource_booking(self):
        """Test resource booking creation."""
        start_time = timezone.now()
        end_time = start_time + timedelta(hours=1)

        booking = ResourceBooking.objects.create(
            calendar=self.calendar,
            resource=self.resource,
            start_time=start_time,
            end_time=end_time,
            booked_by=self.user,
            tenant=self.tenant
        )

        self.assertEqual(booking.resource, self.resource)
        self.assertEqual(booking.calendar, self.calendar)
        self.assertEqual(booking.booked_by, self.user)


class BookingTypeModelTest(TestCase):
    """Test BookingType model functionality."""

    def setUp(self):
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123'
        )
        self.tenant = self.user.tenant
        self.calendar = Calendar.objects.create(
            name='Test Calendar',
            owner=self.user,
            tenant=self.tenant
        )

    def test_booking_type_creation(self):
        """Test booking type creation."""
        booking_type = BookingType.objects.create(
            calendar=self.calendar,
            name='30-minute consultation',
            description='Standard consultation session',
            duration=timedelta(minutes=30),
            booking_slug='consultation-30min',
            tenant=self.tenant
        )

        self.assertEqual(booking_type.name, '30-minute consultation')
        self.assertEqual(booking_type.calendar, self.calendar)
        self.assertEqual(booking_type.duration, timedelta(minutes=30))


class CalendarAPITestCase(APITestCase):
    """Test calendar API endpoints."""

    def setUp(self):
        self.user = User.objects.create_user(
            username='apiuser',
            email='api@example.com',
            password='testpass123'
        )
        self.tenant = self.user.tenant
        self.client.force_authenticate(user=self.user)

        # Create test calendar
        self.calendar = Calendar.objects.create(
            name='API Test Calendar',
            owner=self.user,
            tenant=self.tenant
        )

    def test_calendar_list(self):
        """Test calendar listing API."""
        response = self.client.get('/calendar/api/calendars/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]['name'], 'API Test Calendar')

    def test_calendar_create(self):
        """Test calendar creation API."""
        data = {
            'name': 'New API Calendar',
            'description': 'Created via API',
            'visibility': 'private',
            'color': '#ff0000'
        }
        response = self.client.post('/calendar/api/calendars/', data)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['name'], 'New API Calendar')
        self.assertEqual(response.data['owner'], self.user.id)

    def test_event_create(self):
        """Test event creation API."""
        start_time = timezone.now() + timedelta(hours=1)
        end_time = start_time + timedelta(hours=1)

        data = {
            'calendar': str(self.calendar.id),
            'title': 'API Test Event',
            'description': 'Created via API',
            'start_time': start_time.isoformat(),
            'end_time': end_time.isoformat(),
            'event_type': 'meeting'
        }

        response = self.client.post('/calendar/api/events/', data)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['title'], 'API Test Event')
        self.assertEqual(response.data['calendar'], str(self.calendar.id))

    def test_event_conflict_prevention(self):
        """Test that API prevents double-booking."""
        # Create first event
        start_time = timezone.now() + timedelta(hours=1)
        end_time = start_time + timedelta(hours=1)

        data = {
            'calendar': str(self.calendar.id),
            'title': 'First Event',
            'start_time': start_time.isoformat(),
            'end_time': end_time.isoformat(),
            'event_type': 'meeting'
        }

        response = self.client.post('/calendar/api/events/', data)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        # Try to create conflicting event
        data['title'] = 'Conflicting Event'
        response = self.client.post('/calendar/api/events/', data)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('conflict', response.data['non_field_errors'][0].lower())


class PublicBookingAPITestCase(APITestCase):
    """Test public booking API endpoints."""

    def setUp(self):
        self.user = User.objects.create_user(
            username='bookinguser',
            email='booking@example.com',
            password='testpass123'
        )
        self.tenant = self.user.tenant

        # Create public calendar and booking type
        self.calendar = Calendar.objects.create(
            name='Public Booking Calendar',
            owner=self.user,
            tenant=self.tenant,
            visibility='public'
        )

        self.booking_type = BookingType.objects.create(
            calendar=self.calendar,
            name='Test Booking',
            duration=timedelta(minutes=30),
            booking_slug='test-booking',
            tenant=self.tenant
        )

    def test_public_booking_types(self):
        """Test public booking types endpoint."""
        response = self.client.get('/calendar/api/public/booking-types/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]['name'], 'Test Booking')

    def test_public_availability(self):
        """Test public availability endpoint."""
        response = self.client.get(f'/calendar/api/public/availability/{self.booking_type.booking_slug}/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('available_slots', response.data)

    def test_public_booking_creation(self):
        """Test public booking creation."""
        # Get available slots first
        response = self.client.get(f'/calendar/api/public/availability/{self.booking_type.booking_slug}/')
        available_slots = response.data['available_slots']

        if available_slots:
            slot = available_slots[0]
            booking_data = {
                'booking_slug': self.booking_type.booking_slug,
                'selected_datetime': slot['datetime'],
                'external_name': 'John Doe',
                'external_email': 'john@example.com',
                'external_phone': '+1234567890'
            }

            response = self.client.post('/calendar/api/public/book/', booking_data)
            self.assertEqual(response.status_code, status.HTTP_201_CREATED)
            self.assertIn('event_id', response.data)


class ValidationServiceTestCase(TestCase):
    """Test business logic validation service."""

    def setUp(self):
        self.user = User.objects.create_user(
            username='validationuser',
            email='validation@example.com',
            password='testpass123'
        )
        self.tenant = self.user.tenant
        self.calendar = Calendar.objects.create(
            name='Validation Test Calendar',
            owner=self.user,
            tenant=self.tenant
        )

    def test_event_creation_validation(self):
        """Test event creation validation."""
        start_time = timezone.now() + timedelta(hours=1)
        end_time = start_time + timedelta(hours=1)

        # Should succeed
        try:
            CalendarValidationService.validate_event_creation(
                calendar=self.calendar,
                start_time=start_time,
                end_time=end_time,
                user=self.user
            )
        except CalendarValidationError:
            self.fail("Valid event creation should not raise validation error")

        # Create an event
        CalendarEvent.objects.create(
            calendar=self.calendar,
            title='Test Event',
            start_time=start_time,
            end_time=end_time,
            organizer=self.user,
            tenant=self.tenant
        )

        # Should fail due to conflict
        with self.assertRaises(CalendarValidationError):
            CalendarValidationService.validate_event_creation(
                calendar=self.calendar,
                start_time=start_time,
                end_time=end_time,
                user=self.user
            )

    def test_calendar_sharing_validation(self):
        """Test calendar sharing validation."""
        other_user = User.objects.create_user(
            username='otheruser',
            email='other@example.com',
            password='testpass123'
        )

        # Should succeed
        try:
            CalendarValidationService.validate_calendar_sharing(
                calendar=self.calendar,
                target_user=other_user,
                can_edit=True,
                requesting_user=self.user
            )
        except CalendarValidationError:
            self.fail("Valid calendar sharing should not raise validation error")

        # Should fail - cannot share with self
        with self.assertRaises(CalendarValidationError):
            CalendarValidationService.validate_calendar_sharing(
                calendar=self.calendar,
                target_user=self.user,
                can_edit=True,
                requesting_user=self.user
            )


class SecurityTestCase(TestCase):
    """Test security features."""

    def setUp(self):
        self.user = User.objects.create_user(
            username='securityuser',
            email='security@example.com',
            password='testpass123'
        )
        self.other_user = User.objects.create_user(
            username='othersecurity',
            email='othersecurity@example.com',
            password='testpass123'
        )
        self.tenant = self.user.tenant

        self.calendar = Calendar.objects.create(
            name='Security Test Calendar',
            owner=self.user,
            tenant=self.tenant,
            visibility='private'
        )

    def test_calendar_permissions(self):
        """Test calendar permission enforcement."""
        # Owner should have access
        self.assertTrue(self.calendar.can_view(self.user))
        self.assertTrue(self.calendar.can_edit(self.user))

        # Other user should not have access to private calendar
        self.assertFalse(self.calendar.can_view(self.other_user))
        self.assertFalse(self.calendar.can_edit(self.other_user))

        # Make calendar shared
        self.calendar.visibility = 'shared'
        self.calendar.save()

        from .models import CalendarPermission
        CalendarPermission.objects.create(
            calendar=self.calendar,
            user=self.other_user,
            can_edit=False
        )

        # Other user should now have view access
        self.assertTrue(self.calendar.can_view(self.other_user))
        self.assertFalse(self.calendar.can_edit(self.other_user))


class PerformanceTestCase(TestCase):
    """Test performance optimizations."""

    def setUp(self):
        self.user = User.objects.create_user(
            username='perfuser',
            email='perf@example.com',
            password='testpass123'
        )
        self.tenant = self.user.tenant
        self.calendar = Calendar.objects.create(
            name='Performance Test Calendar',
            owner=self.user,
            tenant=self.tenant
        )

    def test_query_optimization(self):
        """Test that queries are optimized."""
        # Create multiple events
        for i in range(10):
            start_time = timezone.now() + timedelta(hours=i)
            end_time = start_time + timedelta(hours=1)
            CalendarEvent.objects.create(
                calendar=self.calendar,
                title=f'Event {i}',
                start_time=start_time,
                end_time=end_time,
                organizer=self.user,
                tenant=self.tenant
            )

        # Test optimized query
        from .performance import QueryOptimizer
        events = QueryOptimizer.get_events_for_calendars([self.calendar.id])

        # Should not have N+1 query problem
        self.assertEqual(len(events), 10)

        # Check that related objects are prefetched
        for event in events:
            # This should not trigger additional queries
            self.assertEqual(event.calendar.id, self.calendar.id)