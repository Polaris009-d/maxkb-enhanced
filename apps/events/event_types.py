# coding=utf-8
"""
Event type definitions for the document lifecycle.

Each event is a plain dataclass — no Django ORM dependency.
Events are immutable snapshots of what happened.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID, uuid4


@dataclass(frozen=True)
class BaseEvent:
    """Base class for all domain events."""

    event_id: str = field(default_factory=lambda: str(uuid4()))
    timestamp: datetime = field(default_factory=datetime.now)

    @property
    def event_type(self) -> str:
        return self.__class__.__name__


# ── Document Lifecycle Events ──────────────────────────────────────


@dataclass(frozen=True)
class DocumentUploadedEvent(BaseEvent):
    """A new document has been uploaded and is ready for processing."""

    document_id: str = ""
    knowledge_id: str = ""
    file_name: str = ""
    file_size: int = 0
    file_hash: str = ""


@dataclass(frozen=True)
class DocumentParsedEvent(BaseEvent):
    """Document parsing is complete."""

    document_id: str = ""
    knowledge_id: str = ""
    raw_text: str = ""
    page_count: int = 0
    ocr_applied: bool = False
    error: Optional[str] = None


@dataclass(frozen=True)
class DocumentChunkedEvent(BaseEvent):
    """Document has been split into chunks."""

    document_id: str = ""
    chunk_count: int = 0
    avg_chunk_size: int = 0


@dataclass(frozen=True)
class EmbeddingCompletedEvent(BaseEvent):
    """Embedding generation is complete for a document."""

    document_id: str = ""
    knowledge_id: str = ""
    embedded_count: int = 0
    model_name: str = ""
    duration_ms: float = 0.0


@dataclass(frozen=True)
class IndexReadyEvent(BaseEvent):
    """Document is fully indexed and searchable."""

    document_id: str = ""
    knowledge_id: str = ""
    paragraph_count: int = 0
    embedding_count: int = 0


# ── System Events ──────────────────────────────────────────────────


@dataclass(frozen=True)
class ModelChangedEvent(BaseEvent):
    """An AI model configuration has changed."""

    model_id: str = ""
    model_type: str = ""  # EMBEDDING, LLM, etc.
    workspace_id: str = ""
    old_value: Optional[str] = None
    new_value: Optional[str] = None


@dataclass(frozen=True)
class IngestionProgressEvent(BaseEvent):
    """Progress update during ingestion (for WebSocket push)."""

    document_id: str = ""
    stage: str = ""  # parse, chunk, embed, store
    status: str = ""  # started, in_progress, completed, failed
    percentage: int = 0
    message: str = ""
