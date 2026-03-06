# Calendar Integration Guides

## Frontend Integration

### React Component Example

```jsx
import React, { useState, useEffect } from 'react';
import axios from 'axios';

const CalendarIntegration = () => {
  const [calendars, setCalendars] = useState([]);
  const [events, setEvents] = useState([]);
  const [selectedCalendar, setSelectedCalendar] = useState(null);

  // Load user calendars
  useEffect(() => {
    axios.get('/calendar/api/calendars/')
      .then(response => setCalendars(response.data))
      .catch(error => console.error('Error loading calendars:', error));
  }, []);

  // Load events for selected calendar
  useEffect(() => {
    if (selectedCalendar) {
      const startDate = new Date().toISOString().split('T')[0];
      const endDate = new Date(Date.now() + 30 * 24 * 60 * 60 * 1000).toISOString().split('T')[0];

      axios.get(`/calendar/api/events/`, {
        params: {
          calendar: selectedCalendar,
          start_date: startDate,
          end_date: endDate
        }
      })
      .then(response => setEvents(response.data))
      .catch(error => console.error('Error loading events:', error));
    }
  }, [selectedCalendar]);

  const createEvent = async (eventData) => {
    try {
      const response = await axios.post('/calendar/api/events/', {
        ...eventData,
        calendar: selectedCalendar
      });
      // Refresh events
      setEvents(prev => [...prev, response.data]);
      return response.data;
    } catch (error) {
      console.error('Error creating event:', error);
      throw error;
    }
  };

  return (
    <div className="calendar-integration">
      <select
        value={selectedCalendar || ''}
        onChange={(e) => setSelectedCalendar(e.target.value)}
      >
        <option value="">Select Calendar</option>
        {calendars.map(calendar => (
          <option key={calendar.id} value={calendar.id}>
            {calendar.name}
          </option>
        ))}
      </select>

      <div className="events-list">
        {events.map(event => (
          <div key={event.id} className="event-item">
            <h4>{event.title}</h4>
            <p>{event.start_time} - {event.end_time}</p>
            <p>{event.location}</p>
          </div>
        ))}
      </div>
    </div>
  );
};

export default CalendarIntegration;
```

### FullCalendar.js Integration

```javascript
import { Calendar } from '@fullcalendar/core';
import dayGridPlugin from '@fullcalendar/daygrid';
import timeGridPlugin from '@fullcalendar/timegrid';
import listPlugin from '@fullcalendar/list';

document.addEventListener('DOMContentLoaded', function() {
  const calendarEl = document.getElementById('calendar');

  const calendar = new Calendar(calendarEl, {
    plugins: [dayGridPlugin, timeGridPlugin, listPlugin],
    initialView: 'dayGridMonth',
    events: function(fetchInfo, successCallback, failureCallback) {
      // Fetch events from API
      fetch('/calendar/feed.json', {
        headers: {
          'Authorization': `Bearer ${getAuthToken()}`
        }
      })
      .then(response => response.json())
      .then(data => successCallback(data))
      .catch(error => failureCallback(error));
    },
    eventClick: function(info) {
      // Handle event click
      window.location.href = `/calendar/events/${info.event.id}/`;
    },
    dateClick: function(info) {
      // Handle date click - create new event
      const eventData = {
        title: 'New Event',
        start_time: info.dateStr + 'T09:00:00Z',
        end_time: info.dateStr + 'T10:00:00Z',
        calendar: getSelectedCalendarId()
      };

      fetch('/calendar/api/events/', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${getAuthToken()}`
        },
        body: JSON.stringify(eventData)
      })
      .then(response => response.json())
      .then(data => {
        calendar.refetchEvents();
      });
    }
  });

  calendar.render();
});
```

## External System Integration

### Zapier Integration

Create Zaps to connect calendar events with other services:

1. **Trigger**: New calendar event created
2. **Action**: Send Slack notification

```json
// Zapier Webhook Configuration
{
  "url": "https://hooks.zapier.com/hooks/catch/your-webhook-id/",
  "method": "POST",
  "headers": {
    "Content-Type": "application/json"
  },
  "body": {
    "event_type": "calendar.event.created",
    "event_data": "{{event}}"
  }
}
```

### Slack Integration

Post calendar event notifications to Slack:

```python
import requests
import json

def post_event_to_slack(event_data, webhook_url):
    """Post calendar event to Slack channel."""

    message = {
        "blocks": [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": f"📅 {event_data['title']}"
                }
            },
            {
                "type": "section",
                "fields": [
                    {
                        "type": "mrkdwn",
                        "text": f"*When:* {event_data['start_time']}"
                    },
                    {
                        "type": "mrkdwn",
                        "text": f"*Where:* {event_data['location'] or 'TBD'}"
                    }
                ]
            }
        ]
    }

    response = requests.post(webhook_url, json=message)
    return response.status_code == 200
```

### Google Workspace Integration

Sync calendar events with Google Calendar:

```python
from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials

def sync_event_to_google(event_data, google_credentials):
    """Sync calendar event to Google Calendar."""

    creds = Credentials.from_authorized_user_info(google_credentials)
    service = build('calendar', 'v3', credentials=creds)

    google_event = {
        'summary': event_data['title'],
        'description': event_data['description'],
        'start': {
            'dateTime': event_data['start_time'],
            'timeZone': 'UTC',
        },
        'end': {
            'dateTime': event_data['end_time'],
            'timeZone': 'UTC',
        },
        'location': event_data['location'],
    }

    if event_data.get('meeting_link'):
        google_event['hangoutLink'] = event_data['meeting_link']

    result = service.events().insert(
        calendarId='primary',
        body=google_event
    ).execute()

    return result.get('id')
```

## CRM Integration

### Contact Event Creation

Automatically create calendar events when contacts are added:

```python
def create_contact_intro_event(contact_data, calendar_id):
    """Create introduction event when new contact is added."""

    # Schedule event 1 week from now
    start_time = timezone.now() + timedelta(days=7)
    start_time = start_time.replace(hour=10, minute=0, second=0, microsecond=0)
    end_time = start_time + timedelta(hours=1)

    event_data = {
        'calendar': calendar_id,
        'title': f"Introduction with {contact_data['name']}",
        'description': f"Initial meeting with {contact_data['name']} from {contact_data['company']}",
        'start_time': start_time.isoformat(),
        'end_time': end_time.isoformat(),
        'event_type': 'meeting',
        'location': 'Conference Room A'
    }

    response = requests.post(
        '/calendar/api/events/',
        json=event_data,
        headers={'Authorization': f'Bearer {get_token()}'}
    )

    return response.json()
```

### Deal Stage Events

Create events based on deal progression:

```python
DEAL_STAGE_EVENTS = {
    'proposal': {
        'title': 'Proposal Review for {deal_name}',
        'duration_hours': 2,
        'event_type': 'meeting'
    },
    'negotiation': {
        'title': 'Negotiation Session - {deal_name}',
        'duration_hours': 1,
        'event_type': 'call'
    },
    'closing': {
        'title': 'Contract Signing - {deal_name}',
        'duration_hours': 1,
        'event_type': 'meeting'
    }
}

def create_deal_stage_event(deal_data, stage, calendar_id):
    """Create event when deal reaches specific stage."""

    if stage not in DEAL_STAGE_EVENTS:
        return

    event_config = DEAL_STAGE_EVENTS[stage]

    # Schedule event within next 3 business days
    start_time = get_next_business_day(timezone.now(), days=3)
    start_time = start_time.replace(hour=14, minute=0, second=0, microsecond=0)
    end_time = start_time + timedelta(hours=event_config['duration_hours'])

    event_data = {
        'calendar': calendar_id,
        'title': event_config['title'].format(deal_name=deal_data['name']),
        'description': f"Deal: {deal_data['name']} - {deal_data['company']}",
        'start_time': start_time.isoformat(),
        'end_time': end_time.isoformat(),
        'event_type': event_config['event_type']
    }

    response = requests.post(
        '/calendar/api/events/',
        json=event_data,
        headers={'Authorization': f'Bearer {get_token()}'}
    )

    return response.json()

def get_next_business_day(start_date, days):
    """Get next business day after specified days."""
    current = start_date
    business_days_added = 0

    while business_days_added < days:
        current += timedelta(days=1)
        if current.weekday() < 5:  # Monday to Friday
            business_days_added += 1

    return current
```

## Email Integration

### Outlook Add-in

Create Outlook add-in for calendar integration:

```javascript
// Outlook Add-in Manifest
{
  "version": "1.0.0",
  "manifestVersion": "1.1",
  "id": "calendar-integration",
  "name": "Calendar Integration",
  "description": "Sync Outlook events with your calendar",
  "permissions": ["ReadWriteMailbox"],
  "hosts": ["Mailbox"],
  "requirements": {
    "scopes": ["https://graph.microsoft.com/Calendars.ReadWrite"]
  }
}
```

### Gmail Extension

Chrome extension for Gmail calendar integration:

```javascript
// background.js
chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
  if (request.action === 'createEvent') {
    fetch('https://your-domain.com/calendar/api/events/', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${getStoredToken()}`
      },
      body: JSON.stringify(request.eventData)
    })
    .then(response => response.json())
    .then(data => sendResponse({success: true, data}))
    .catch(error => sendResponse({success: false, error}));
  }
  return true; // Keep message channel open
});
```

## Mobile App Integration

### React Native Calendar

```jsx
import React, { useState, useEffect } from 'react';
import { Calendar } from 'react-native-calendars';

const MobileCalendar = () => {
  const [events, setEvents] = useState({});
  const [selectedDate, setSelectedDate] = useState('');

  useEffect(() => {
    loadEvents();
  }, []);

  const loadEvents = async () => {
    try {
      const response = await fetch('/calendar/api/events/', {
        headers: {
          'Authorization': `Bearer ${getToken()}`
        }
      });
      const eventsData = await response.json();

      // Format for react-native-calendars
      const markedDates = {};
      eventsData.forEach(event => {
        const date = event.start_time.split('T')[0];
        markedDates[date] = {
          marked: true,
          dotColor: '#3788d8',
          selectedColor: selectedDate === date ? '#28a745' : undefined
        };
      });

      setEvents(markedDates);
    } catch (error) {
      console.error('Error loading events:', error);
    }
  };

  return (
    <Calendar
      markedDates={events}
      onDayPress={(day) => {
        setSelectedDate(day.dateString);
        // Navigate to day view
      }}
      theme={{
        todayTextColor: '#3788d8',
        selectedDayBackgroundColor: '#3788d8',
      }}
    />
  );
};

export default MobileCalendar;
```

## Webhook Integration

### Event Change Notifications

Handle real-time event updates:

```python
import json
from django.http import HttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

@csrf_exempt
@require_POST
def calendar_webhook(request):
    """Handle calendar webhook notifications."""

    try:
        payload = json.loads(request.body)
        event_type = payload.get('event_type')

        if event_type == 'calendar.event.created':
            handle_event_created(payload['data'])
        elif event_type == 'calendar.event.updated':
            handle_event_updated(payload['data'])
        elif event_type == 'calendar.event.deleted':
            handle_event_deleted(payload['data'])

        return HttpResponse(status=200)

    except Exception as e:
        logger.error(f"Webhook processing failed: {e}")
        return HttpResponse(status=500)

def handle_event_created(event_data):
    """Handle event creation notification."""
    # Update external systems
    # Send notifications
    # Update caches
    pass

def handle_event_updated(event_data):
    """Handle event update notification."""
    # Sync changes to external calendars
    # Update notifications
    pass

def handle_event_deleted(event_data):
    """Handle event deletion notification."""
    # Clean up related data
    # Cancel notifications
    pass
```

## API Rate Limiting Handling

### Client-Side Rate Limit Handling

```javascript
class ApiClient {
  constructor() {
    this.retryQueue = [];
    this.isRateLimited = false;
  }

  async request(url, options = {}) {
    if (this.isRateLimited) {
      return new Promise((resolve) => {
        this.retryQueue.push({ url, options, resolve });
      });
    }

    try {
      const response = await fetch(url, {
        ...options,
        headers: {
          'Authorization': `Bearer ${this.token}`,
          ...options.headers
        }
      });

      // Check rate limit headers
      const remaining = response.headers.get('X-RateLimit-Remaining');
      const resetTime = response.headers.get('X-RateLimit-Reset');

      if (response.status === 429) {
        this.handleRateLimit(resetTime);
        throw new Error('Rate limited');
      }

      if (remaining && parseInt(remaining) < 10) {
        console.warn('Approaching rate limit');
      }

      return response;

    } catch (error) {
      if (error.message === 'Rate limited') {
        throw error;
      }
      throw new Error(`API request failed: ${error.message}`);
    }
  }

  handleRateLimit(resetTime) {
    this.isRateLimited = true;

    const resetDate = new Date(parseInt(resetTime) * 1000);
    const waitTime = resetDate - new Date();

    setTimeout(() => {
      this.isRateLimited = false;
      // Process queued requests
      this.processRetryQueue();
    }, waitTime);
  }

  async processRetryQueue() {
    while (this.retryQueue.length > 0) {
      const { url, options, resolve } = this.retryQueue.shift();
      try {
        const response = await this.request(url, options);
        resolve(response);
      } catch (error) {
        // Handle retry failures
        console.error('Retry failed:', error);
      }
    }
  }
}
```

## Error Handling Strategies

### Circuit Breaker Pattern

```python
import time
from functools import wraps

class CircuitBreaker:
    def __init__(self, failure_threshold=5, recovery_timeout=60):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.failure_count = 0
        self.last_failure_time = None
        self.state = 'CLOSED'  # CLOSED, OPEN, HALF_OPEN

    def call(self, func, *args, **kwargs):
        if self.state == 'OPEN':
            if time.time() - self.last_failure_time > self.recovery_timeout:
                self.state = 'HALF_OPEN'
            else:
                raise Exception("Circuit breaker is OPEN")

        try:
            result = func(*args, **kwargs)
            self.on_success()
            return result
        except Exception as e:
            self.on_failure()
            raise e

    def on_success(self):
        self.failure_count = 0
        self.state = 'CLOSED'

    def on_failure(self):
        self.failure_count += 1
        self.last_failure_time = time.time()

        if self.failure_count >= self.failure_threshold:
            self.state = 'OPEN'

def circuit_breaker(failure_threshold=5, recovery_timeout=60):
    breaker = CircuitBreaker(failure_threshold, recovery_timeout)

    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            return breaker.call(func, *args, **kwargs)
        return wrapper
    return decorator

# Usage
@circuit_breaker(failure_threshold=3, recovery_timeout=30)
def create_calendar_event(event_data):
    """Create calendar event with circuit breaker protection."""
    response = requests.post('/calendar/api/events/', json=event_data)
    response.raise_for_status()
    return response.json()
```

This comprehensive integration guide covers the most common integration patterns and provides practical examples for connecting the calendar system with various platforms and use cases.