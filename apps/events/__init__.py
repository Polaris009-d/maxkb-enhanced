# coding=utf-8
"""
Event bus — decoupled pub/sub for document lifecycle events.

Uses Django signals as the transport layer, with a clean event
interface for: document uploaded, parsed, embedded, indexed.

Usage:
    from events.bus import EventBus
    from events.event_types import DocumentParsedEvent

    EventBus.publish(DocumentParsedEvent(document_id="...", text="..."))
"""
from events.bus import EventBus
from events.event_types import (
    BaseEvent,
    DocumentUploadedEvent,
    DocumentParsedEvent,
    DocumentChunkedEvent,
    EmbeddingCompletedEvent,
    IndexReadyEvent,
    ModelChangedEvent,
    IngestionProgressEvent,
)

__all__ = [
    "EventBus",
    "BaseEvent",
    "DocumentUploadedEvent",
    "DocumentParsedEvent",
    "DocumentChunkedEvent",
    "EmbeddingCompletedEvent",
    "IndexReadyEvent",
    "ModelChangedEvent",
    "IngestionProgressEvent",
]
