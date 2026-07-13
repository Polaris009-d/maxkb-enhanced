# coding=utf-8
"""
Chat service — high-level RAG pipeline orchestration.

Wraps the low-level PipelineManage with a clean interface for:
    - SIMPLE RAG: retrieve → generate
    - WORK_FLOW: full workflow execution

Usage:
    from rag.services.chat_service import ChatService

    service = ChatService()
    result = service.chat(
        application_id="...",
        message="奖学金怎么申请",
        chat_id="...",
        user_id="...",
    )
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger("maxkb.rag")


class ChatContext:
    """Structured context passed through the RAG pipeline."""

    def __init__(
        self,
        application_id: str,
        message: str,
        chat_id: Optional[str] = None,
        chat_record_id: Optional[str] = None,
        user_id: Optional[str] = None,
        user_type: Optional[str] = None,
        stream: bool = True,
        debug: bool = False,
    ):
        self.application_id = application_id
        self.message = message
        self.chat_id = chat_id
        self.chat_record_id = chat_record_id
        self.user_id = user_id
        self.user_type = user_type
        self.stream = stream
        self.debug = debug


class ChatResult:
    """Result from the RAG pipeline."""

    def __init__(self):
        self.answer: str = ""
        self.paragraphs: List[Dict] = []
        self.knowledge_sources: List[Dict] = []
        self.message_tokens: int = 0
        self.answer_tokens: int = 0
        self.run_time: float = 0.0

    def to_dict(self) -> Dict:
        return {
            "answer": self.answer,
            "paragraphs": self.paragraphs,
            "knowledge_sources": self.knowledge_sources,
            "message_tokens": self.message_tokens,
            "answer_tokens": self.answer_tokens,
            "run_time": self.run_time,
        }


class ChatService:
    """High-level RAG chat service.

    Encapsulates the full pipeline: query → retrieve → generate.
    Uses the existing PipelineManage infrastructure for execution.
    """

    @staticmethod
    def _build_pipeline(
        problem_optimization: bool = False,
        base_to_response=None,
        debug: bool = False,
    ):
        """Build the RAG pipeline with appropriate steps."""
        from application.chat_pipeline.pipeline_manage import PipelineManage
        from application.chat_pipeline.step.chat_step.impl.base_chat_step import (
            BaseChatStep,
        )
        from application.chat_pipeline.step.generate_human_message_step.impl.base_generate_human_message_step import (
            BaseGenerateHumanMessageStep,
        )
        from application.chat_pipeline.step.reset_problem_step.impl.base_reset_problem_step import (
            BaseResetProblemStep,
        )
        from application.chat_pipeline.step.search_dataset_step.impl.base_search_dataset_step import (
            BaseSearchDatasetStep,
        )

        builder = PipelineManage.builder()
        if problem_optimization:
            builder.append_step(BaseResetProblemStep)

        pipeline = (
            builder.append_step(BaseSearchDatasetStep)
            .append_step(BaseGenerateHumanMessageStep)
            .append_step(BaseChatStep)
            .build()
        )
        return pipeline

    @staticmethod
    def get_application_config(application_id: str) -> Dict:
        """Get the active application configuration.

        Args:
            application_id: The application UUID.

        Returns:
            Dict with keys: model_setting, knowledge_setting, type, etc.
        """
        from application.models import Application, ApplicationVersion
        from django.db.models import QuerySet

        app = (
            QuerySet(ApplicationVersion)
            .filter(application_id=application_id)
            .order_by("-create_time")
            .first()
        )
        if not app:
            app = QuerySet(Application).filter(id=application_id).first()
        if not app:
            raise ValueError(f"Application {application_id} not found")

        return {
            "id": str(app.id) if hasattr(app, "id") else "",
            "type": app.type,
            "model_id": str(app.model_id) if app.model_id else None,
            "model_setting": app.model_setting or {},
            "knowledge_setting": app.knowledge_setting or {},
            "problem_optimization": getattr(app, "problem_optimization", False),
            "workspace_id": getattr(app, "workspace_id", "default"),
        }

    @staticmethod
    def _resolve_model(application_id: str) -> Optional[Any]:
        """Resolve the chat model for an application."""
        from models_provider.tools import get_model_instance_by_model_workspace_id

        config = ChatService.get_application_config(application_id)
        model_id = config.get("model_id")
        workspace_id = config.get("workspace_id")
        if not model_id:
            return None
        return get_model_instance_by_model_workspace_id(model_id, workspace_id)
