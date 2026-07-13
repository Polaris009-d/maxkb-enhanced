# coding=utf-8
"""
Domain models — pure Python objects representing core business concepts.

These are framework-agnostic and can be used across Django apps,
Celery tasks, and future microservices without ORM coupling.
"""
from domain.document import (
    Chunk,
    DocumentStatus,
    DocumentState,
    IngestionStage,
    ParsedDocument,
)
from domain.conversation import Answer, ChatContext, Message, Question
from domain.embedding import EmbeddedChunk, EmbeddingVector, SearchHit, SearchQuery

__all__ = [
    # Document lifecycle
    "DocumentState",
    "DocumentStatus",
    "IngestionStage",
    "ParsedDocument",
    "Chunk",
    # Embedding
    "EmbeddingVector",
    "EmbeddedChunk",
    "SearchQuery",
    "SearchHit",
    # Conversation
    "Message",
    "Question",
    "Answer",
    "ChatContext",
]
