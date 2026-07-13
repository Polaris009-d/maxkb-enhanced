# coding=utf-8
"""
Event bus — publish/subscribe using Django signals.

Provides a decoupled communication layer between ingestion, retrieval,
and application components.

Usage:
    # Subscribe
    @EventBus.on(DocumentParsedEvent)
    def handle_parsed(event: DocumentParsedEvent):
        print(f"Document {event.document_id} parsed: {len(event.raw_text)} chars")

    # Publish
    EventBus.publish(DocumentParsedEvent(
        document_id="abc123",
        knowledge_id="kb-1",
        raw_text="...",
    ))
"""

from __future__ import annotations

import logging
from typing import Any, Callable, Dict, List, Type

import django.dispatch

from events.event_types import BaseEvent

logger = logging.getLogger("maxkb.events")

# Django signal used as the transport layer
_event_signal = django.dispatch.Signal()

# Registry: event_type → list of handlers
_handlers: Dict[str, List[Callable]] = {}


class EventBus:
    """Central event bus for publishing and subscribing to domain events."""

    @staticmethod
    def publish(event: BaseEvent) -> None:
        """Publish an event to all registered handlers.

        Args:
            event: Any BaseEvent subclass instance.

        Handlers are called synchronously. For async processing,
        handlers should defer to Celery tasks internally.
        """
        event_type = event.event_type

        # Dispatch via Django signal (for signal-based subscribers)
        try:
            _event_signal.send(sender=event.__class__, event=event)
        except Exception:
            logger.warning(f"Signal handler error for {event_type}", exc_info=True)

        # Dispatch via registry (for decorator-based subscribers)
        for handler in _handlers.get(event_type, []):
            try:
                handler(event)
            except Exception:
                logger.warning(
                    f"Handler {handler.__name__} failed for {event_type}",
                    exc_info=True,
                )

    @staticmethod
    def on(event_class: Type[BaseEvent]) -> Callable:
        """Decorator to register a handler for an event type.

        Args:
            event_class: The event class to subscribe to.

        Returns:
            Decorator function.

        Example:
            @EventBus.on(DocumentParsedEvent)
            def handle_parse(event: DocumentParsedEvent):
                ...
        """
        def decorator(handler: Callable) -> Callable:
            event_type = event_class.__name__
            if event_type not in _handlers:
                _handlers[event_type] = []
            _handlers[event_type].append(handler)
            logger.debug(f"Registered handler {handler.__name__} for {event_type}")
            return handler
        return decorator

    @staticmethod
    def subscribe(event_class: Type[BaseEvent], handler: Callable) -> None:
        """Programmatically subscribe to an event type.

        Args:
            event_class: The event class to subscribe to.
            handler: Callable that receives the event instance.
        """
        event_type = event_class.__name__
        if event_type not in _handlers:
            _handlers[event_type] = []
        _handlers[event_type].append(handler)

    @staticmethod
    def clear() -> None:
        """Clear all registered handlers (useful for testing)."""
        _handlers.clear()

    @staticmethod
    def get_handlers(event_class: Type[BaseEvent]) -> List[Callable]:
        """Get all registered handlers for an event type."""
        return _handlers.get(event_class.__name__, [])
