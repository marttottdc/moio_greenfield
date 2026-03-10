# myapp/event_bus.py
from collections import defaultdict
from typing import Callable, Any


class EventBus:
    def __init__(self):
        # Store subscribers as a dictionary of event types to lists of callbacks
        self._subscribers = defaultdict(list)

    def subscribe(self, event_type: str, callback: Callable):
        """Register a callback for a specific event type."""
        self._subscribers[event_type].append(callback)

    def unsubscribe(self, event_type: str, callback: Callable):
        """Remove a callback from a specific event type."""
        if event_type in self._subscribers:
            self._subscribers[event_type].remove(callback)

    def publish(self, event_type: str, *args, **kwargs):
        """Dispatch an event to all subscribers of the event type."""
        if event_type in self._subscribers:
            for callback in self._subscribers[event_type]:
                callback(*args, **kwargs)


# Singleton instance
event_bus = EventBus()
