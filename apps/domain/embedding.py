# coding=utf-8
"""
Embedding and vector search domain models.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional
from uuid import UUID, uuid4


class SearchStrategy(str, Enum):
    """Available search strategies."""

    EMBEDDING = "embedding"
    KEYWORDS = "keywords"
    BLEND = "blend"
    HYBRID = "hybrid"


@dataclass
class EmbeddingVector:
    """A single embedding vector."""

    dimension: int
    values: List[float]
    model_name: str = ""
    created_at: datetime = field(default_factory=datetime.now)

    def __len__(self) -> int:
        return len(self.values)

    def to_list(self) -> List[float]:
        return self.values


@dataclass
class EmbeddedChunk:
    """A chunk that has been embedded and indexed."""

    id: UUID = field(default_factory=uuid4)
    chunk_id: UUID = field(default_factory=uuid4)
    document_id: UUID = field(default_factory=uuid4)
    knowledge_id: UUID = field(default_factory=uuid4)
    embedding: Optional[EmbeddingVector] = None
    search_vector: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)
    indexed_at: datetime = field(default_factory=datetime.now)


@dataclass
class SearchQuery:
    """A search query with its embedding."""

    text: str
    embedding: Optional[EmbeddingVector] = None
    top_n: int = 5
    similarity_threshold: float = 0.3
    strategy: SearchStrategy = SearchStrategy.HYBRID
    knowledge_ids: List[str] = field(default_factory=list)
    exclude_document_ids: List[str] = field(default_factory=list)


@dataclass
class SearchHit:
    """A single search result."""

    paragraph_id: str = ""
    chunk_id: str = ""
    content: str = ""
    title: str = ""
    document_id: str = ""
    knowledge_id: str = ""
    score: float = 0.0
    similarity: float = 0.0
    rerank_score: Optional[float] = None
