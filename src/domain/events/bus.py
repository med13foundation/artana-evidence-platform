from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable

from .base import DomainEvent

EventHandler = Callable[[DomainEvent], None]


class DomainEventBus:
    """Simple in-memory synchronous event bus."""

    def __init__(self) -> None:
        self._subscribers: defaultdict[str, list[EventHandler]] = defaultdict(list)

    def publish(self, event: DomainEvent) -> None:
        """Publish an event to all subscribers."""
        for handler in list(self._subscribers.get(event.event_type, [])):
            handler(event)

    def subscribe(self, event_type: str, handler: EventHandler) -> None:
        """Register a handler for the given event type."""
        self._subscribers[event_type].append(handler)

    def unsubscribe(self, event_type: str, handler: EventHandler) -> None:
        """Remove a handler if it is registered."""
        handlers = self._subscribers.get(event_type)
        if not handlers:
            return
        if handler in handlers:
            handlers.remove(handler)


domain_event_bus = DomainEventBus()


__all__ = ["DomainEventBus", "EventHandler", "domain_event_bus"]
