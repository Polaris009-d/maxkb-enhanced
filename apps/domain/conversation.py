# coding=utf-8
"""
Conversation domain models — chat, messages, RAG context.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID, uuid4


class MessageRole(str):
    """Message roles in a conversation."""

    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "ai"


@dataclass
class Message:
    """A single message in a conversation."""

    role: str
    content: str
    timestamp: datetime = field(default_factory=datetime.now)

    @classmethod
    def system(cls, content: str) -> Message:
        return cls(role=MessageRole.SYSTEM, content=content)

    @classmethod
    def user(cls, content: str) -> Message:
        return cls(role=MessageRole.USER, content=content)

    @classmethod
    def assistant(cls, content: str) -> Message:
        return cls(role=MessageRole.ASSISTANT, content=content)


@dataclass
class Question:
    """A user's question with optional rewriting."""

    original: str
    rewritten: Optional[str] = None
    embedding: Optional[List[float]] = None

    @property
    def effective(self) -> str:
        return self.rewritten or self.original


@dataclass
class Answer:
    """An LLM-generated answer with metadata."""

    text: str
    tokens_used: int = 0
    model: str = ""
    cached: bool = False
    reasoning: str = ""
    generated_at: datetime = field(default_factory=datetime.now)


@dataclass
class ChatContext:
    """Full context for a RAG chat turn."""

    question: Question
    messages: List[Message] = field(default_factory=list)
    retrieved_chunks: List[Any] = field(default_factory=list)
    system_prompt: str = ""
    user_prompt_template: str = ""
    model_id: Optional[str] = None
    temperature: float = 0.7
    max_tokens: int = 2048
