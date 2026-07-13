# coding=utf-8
"""
Document lifecycle domain models.

Represents the states a document goes through:
    Uploaded → Parsing → Parsed → Chunking → Embedding → Indexed
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional
from uuid import UUID, uuid4


# ── Enums ──────────────────────────────────────────────────────────


class IngestionStage(str, Enum):
    """Stages of the document ingestion pipeline."""

    PARSE = "parse"
    CHUNK = "chunk"
    EMBED = "embed"
    STORE = "store"


class DocumentState(str, Enum):
    """Document processing state per stage."""

    PENDING = "0"
    STARTED = "1"
    SUCCESS = "2"
    FAILURE = "3"
    REVOKE = "4"
    REVOKED = "5"
    IGNORED = "n"


class DocumentStatus:
    """Composite status tracking for multi-stage document processing.

    Compatible with the existing MaxKB status bitfield format.
    """

    def __init__(self, status_str: str = "nnnn"):
        self.embedding = DocumentState(status_str[0] if len(status_str) > 0 else "n")
        self.generate_problem = DocumentState(status_str[1] if len(status_str) > 1 else "n")
        self.sync = DocumentState(status_str[2] if len(status_str) > 2 else "n")
        self.tokenize = DocumentState(status_str[3] if len(status_str) > 3 else "n")

    def __str__(self) -> str:
        return f"{self.embedding.value}{self.generate_problem.value}{self.sync.value}{self.tokenize.value}"

    @classmethod
    def success(cls) -> DocumentStatus:
        return cls("2222")

    @classmethod
    def pending(cls) -> DocumentStatus:
        return cls("0000")

    @property
    def is_ready(self) -> bool:
        return self.embedding == DocumentState.SUCCESS and self.tokenize == DocumentState.SUCCESS


# ── Domain Models ───────────────────────────────────────────────────


@dataclass
class ParsedDocument:
    """Document after parsing, before chunking."""

    id: UUID = field(default_factory=uuid4)
    name: str = ""
    raw_text: str = ""
    file_size: int = 0
    file_hash: str = ""
    page_count: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)
    parsed_at: datetime = field(default_factory=datetime.now)

    @property
    def char_count(self) -> int:
        return len(self.raw_text)

    @property
    def is_scanned(self) -> bool:
        """Heuristic: if very little text was extracted, it's likely scanned."""
        return self.char_count < 100 or self.raw_text.count("![image]") > self.char_count / 100


@dataclass
class Chunk:
    """A semantic chunk of document text."""

    id: UUID = field(default_factory=uuid4)
    document_id: UUID = field(default_factory=uuid4)
    position: int = 0
    content: str = ""
    title: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.now)

    def to_embedding_text(self) -> str:
        """Build the text that will be embedded for this chunk."""
        if self.title:
            return f"{self.title}\n{self.content}"
        return self.content
