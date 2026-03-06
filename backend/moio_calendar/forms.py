from django import forms
from moio_calendar.models import CalendarEvent, AvailabilitySlot, SharedResource, BookingType, Calendar


class CalendarForm(forms.ModelForm):
    class Meta:
        model = Calendar
        fields = ['name', 'description', 'visibility', 'color']
        widgets = {
            'description': forms.Textarea(attrs={'rows': 3}),
            'color': forms.TextInput(attrs={'type': 'color'}),
        }


class CalendarEventForm(forms.ModelForm):
    class Meta:
        model = CalendarEvent
        fields = ['calendar', 'title', 'description', 'start_time', 'end_time', 'location', 'event_type']
        widgets = {
            'start_time': forms.DateTimeInput(attrs={'type': 'datetime-local'}),
            'end_time': forms.DateTimeInput(attrs={'type': 'datetime-local'}),
            'description': forms.Textarea(attrs={'rows': 3}),
        }


class AvailabilitySlotForm(forms.ModelForm):
    slot_duration = forms.DurationField(
        initial='00:30:00',
        help_text='Duration of each bookable slot (HH:MM:SS format, e.g., 00:30:00 for 30 minutes)'
    )
    
    class Meta:
        model = AvailabilitySlot
        fields = ['day_of_week', 'start_time', 'end_time', 'slot_duration', 'is_active']
        widgets = {
            'start_time': forms.TimeInput(attrs={'type': 'time'}),
            'end_time': forms.TimeInput(attrs={'type': 'time'}),
        }


class SharedResourceForm(forms.ModelForm):
    class Meta:
        model = SharedResource
        fields = ['name', 'description', 'capacity', 'location', 'resource_type']
        widgets = {
            'description': forms.Textarea(attrs={'rows': 3}),
        }


class BookingTypeForm(forms.ModelForm):
    class Meta:
        model = BookingType
        fields = ['name', 'description', 'duration', 'booking_slug', 'is_active']
        widgets = {
            'description': forms.Textarea(attrs={'rows': 3}),
            'booking_slug': forms.TextInput(attrs={'placeholder': 'unique-booking-url'}),
        }
