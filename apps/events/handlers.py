# coding=utf-8
"""
Default event handlers — wire up the ingestion pipeline.

These handlers demonstrate the event-driven architecture.
In production, they would trigger Celery tasks for async processing.

Registered in events/apps.py during Django startup.
"""

from __future__ import annotations

import logging

from events.bus import EventBus
from events.event_types import (
    DocumentChunkedEvent,
    DocumentParsedEvent,
    DocumentUploadedEvent,
    EmbeddingCompletedEvent,
    IndexReadyEvent,
    IngestionProgressEvent,
    ModelChangedEvent,
)

logger = logging.getLogger("maxkb.events.handlers")


# ── Document Lifecycle Handlers ────────────────────────────────────


@EventBus.on(DocumentUploadedEvent)
def on_document_uploaded(event: DocumentUploadedEvent) -> None:
    """Trigger parsing when a document is uploaded."""
    logger.info(
        f"[EVENT] Document uploaded: {event.file_name} "
        f"({event.file_size} bytes) → knowledge {event.knowledge_id[:8]}..."
    )
    # In production: trigger Celery task for async parsing
    # from ingestion.tasks import parse_document
    # parse_document.delay(document_id=event.document_id)


@EventBus.on(DocumentParsedEvent)
def on_document_parsed(event: DocumentParsedEvent) -> None:
    """Trigger chunking after parsing."""
    char_count = len(event.raw_text) if event.raw_text else 0
    ocr_note = " (OCR applied)" if event.ocr_applied else ""
    logger.info(
        f"[EVENT] Document parsed: {event.document_id[:8]}... "
        f"→ {char_count} chars{ocr_note}"
    )
    if event.error:
        logger.warning(f"[EVENT] Parse error for {event.document_id}: {event.error}")


@EventBus.on(DocumentChunkedEvent)
def on_document_chunked(event: DocumentChunkedEvent) -> None:
    """Trigger embedding after chunking."""
    logger.info(
        f"[EVENT] Document chunked: {event.document_id[:8]}... "
        f"→ {event.chunk_count} chunks (avg {event.avg_chunk_size} chars)"
    )


@EventBus.on(EmbeddingCompletedEvent)
def on_embedding_completed(event: EmbeddingCompletedEvent) -> None:
    """Update search indexes after embedding."""
    logger.info(
        f"[EVENT] Embedding completed: {event.document_id[:8]}... "
        f"→ {event.embedded_count} vectors "
        f"({event.model_name}, {event.duration_ms:.0f}ms)"
    )


@EventBus.on(IndexReadyEvent)
def on_index_ready(event: IndexReadyEvent) -> None:
    """Notify that a document is fully indexed and searchable."""
    logger.info(
        f"[EVENT] Index ready: {event.document_id[:8]}... "
        f"→ {event.paragraph_count} paragraphs, "
        f"{event.embedding_count} embeddings"
    )
    # In production: push WebSocket notification
    # from events.bridge import publish_to_websocket
    # publish_to_websocket(event)


# ── Progress Events ────────────────────────────────────────────────


@EventBus.on(IngestionProgressEvent)
def on_ingestion_progress(event: IngestionProgressEvent) -> None:
    """Forward progress events to WebSocket clients."""
    logger.debug(
        f"[EVENT] Progress: {event.document_id[:8]}... "
        f"stage={event.stage} status={event.status} {event.percentage}%"
    )
    # In production: bridge to Django Channels
    try:
        from common.websocket.progress_publisher import IndexProgressPublisher

        IndexProgressPublisher.publish_progress(
            document_id=event.document_id,
            stage=event.stage,
            status=event.status,
            percentage=event.percentage,
            message=event.message,
        )
    except Exception:
        pass  # Channels not available (e.g., management commands)


# ── System Events ──────────────────────────────────────────────────


@EventBus.on(ModelChangedEvent)
def on_model_changed(event: ModelChangedEvent) -> None:
    """Handle model changes that require re-processing."""
    logger.info(
        f"[EVENT] Model changed: {event.model_id[:8]}... "
        f"type={event.model_type}"
    )
    if event.model_type == "EMBEDDING":
        # Trigger re-embedding of affected documents
        logger.info(
            f"[EVENT] Embedding model changed → re-embedding needed "
            f"for workspace {event.workspace_id}"
        )
