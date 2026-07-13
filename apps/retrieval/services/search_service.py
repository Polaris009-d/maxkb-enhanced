# coding=utf-8
"""
Unified search service for multi-strategy retrieval.

Dispatches to the appropriate search strategy (embedding, keyword, hybrid, blend)
and applies post-retrieval filters (permission, reranker).

Usage:
    from retrieval.services.search_service import SearchService

    results = SearchService.search(
        query_text="奖学金如何申请",
        knowledge_ids=["..."],
        top_n=5,
        similarity=0.3,
        search_mode="hybrid",
    )
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from common.config.embedding_config import VectorStore, ModelManage
from common.utils.permission_filter import PermissionFilter
from knowledge.models import Knowledge, SearchMode
from models_provider.tools import get_model, get_model_by_id, get_model_default_params

logger = logging.getLogger("maxkb.retrieval")


class SearchResult:
    """Normalized search result across all strategies."""

    def __init__(
        self,
        paragraph_id: str = "",
        document_id: str = "",
        knowledge_id: str = "",
        content: str = "",
        title: str = "",
        score: float = 0.0,
        similarity: float = 0.0,
    ):
        self.paragraph_id = paragraph_id
        self.document_id = document_id
        self.knowledge_id = knowledge_id
        self.content = content
        self.title = title
        self.score = score
        self.similarity = similarity

    def to_dict(self) -> Dict:
        return {
            "paragraph_id": self.paragraph_id,
            "document_id": self.document_id,
            "knowledge_id": self.knowledge_id,
            "content": self.content,
            "title": self.title,
            "comprehensive_score": self.score,
            "similarity": self.similarity,
        }


class SearchService:
    """Unified search service for multi-strategy retrieval."""

    @staticmethod
    def _get_embedding_model(knowledge_ids: List[str], workspace_id: str = "default"):
        """Get the embedding model for the given knowledge bases."""
        if not knowledge_ids:
            return None, None

        kb = Knowledge.objects.filter(id__in=knowledge_ids).first()
        if not kb or not kb.embedding_model_id:
            return None, None

        model = get_model_by_id(kb.embedding_model_id, workspace_id)
        if model.model_type != "EMBEDDING":
            return None, None

        default_params = get_model_default_params(model)
        embedding_model = ModelManage.get_model(
            kb.embedding_model_id,
            lambda _id: get_model(model, **{**default_params}),
        )
        return embedding_model, model

    @staticmethod
    def search(
        query_text: str,
        knowledge_ids: List[str],
        top_n: int = 5,
        similarity: float = 0.3,
        search_mode: str = "hybrid",
        exclude_document_ids: Optional[List[str]] = None,
        exclude_paragraph_ids: Optional[List[str]] = None,
        user_id: Optional[str] = None,
        user_role: str = "viewer",
        workspace_id: str = "default",
    ) -> List[Dict]:
        """Execute a search query across knowledge bases.

        Args:
            query_text: The user's question.
            knowledge_ids: List of knowledge base UUIDs to search.
            top_n: Number of results to return.
            similarity: Minimum similarity threshold (0.0-1.0).
            search_mode: One of 'embedding', 'keywords', 'blend', 'hybrid'.
            exclude_document_ids: Document IDs to exclude.
            exclude_paragraph_ids: Paragraph IDs to exclude.
            user_id: Current user ID for permission filtering.
            user_role: 'admin' or 'viewer'.
            workspace_id: Workspace ID.

        Returns:
            List of dicts with keys: paragraph_id, content, similarity, etc.
        """
        if not knowledge_ids:
            return []

        embedding_model, _ = SearchService._get_embedding_model(knowledge_ids, workspace_id)
        if embedding_model is None:
            logger.warning("No embedding model available for search")
            return []

        vector = VectorStore.get_embedding_vector()
        query_embedding = embedding_model.embed_query(query_text)

        # Execute search via vector store
        raw_results = vector.query(
            query_text,
            query_embedding,
            knowledge_ids,
            None,
            exclude_document_ids or [],
            exclude_paragraph_ids or [],
            True,
            top_n,
            similarity,
            SearchMode(search_mode),
        )

        if not raw_results:
            return []

        # Enrich results with paragraph content
        from knowledge.models import Paragraph
        from django.db.models import QuerySet

        paragraph_ids = [r.get("paragraph_id") for r in raw_results if r.get("paragraph_id")]
        paragraphs = QuerySet(Paragraph).filter(id__in=paragraph_ids).values(
            "id", "content", "title", "document_id", "knowledge_id"
        )
        para_map = {str(p["id"]): p for p in paragraphs}

        results = []
        for raw in raw_results:
            pid = raw.get("paragraph_id", "")
            para = para_map.get(pid, {})
            results.append(
                SearchResult(
                    paragraph_id=pid,
                    document_id=str(para.get("document_id", "")),
                    knowledge_id=str(para.get("knowledge_id", "")),
                    content=para.get("content", ""),
                    title=para.get("title", ""),
                    score=raw.get("comprehensive_score", raw.get("similarity", 0)),
                    similarity=raw.get("similarity", 0),
                ).to_dict()
            )

        return results

    @staticmethod
    def search_with_rerank(
        query_text: str,
        knowledge_ids: List[str],
        top_n: int = 5,
        similarity: float = 0.3,
        search_mode: str = "embedding",
        user_id: Optional[str] = None,
        user_role: str = "viewer",
        workspace_id: str = "default",
    ) -> List[Dict]:
        """Search and apply Cross-Encoder reranking.

        First retrieves top-20 candidates, then re-ranks with Cross-Encoder
        (or embedding fallback) down to top_n results.
        """
        # Get more candidates for reranking
        candidates = SearchService.search(
            query_text=query_text,
            knowledge_ids=knowledge_ids,
            top_n=min(top_n * 4, 20),
            similarity=max(similarity * 0.5, 0.1),
            search_mode=search_mode,
            user_id=user_id,
            user_role=user_role,
            workspace_id=workspace_id,
        )

        if len(candidates) <= top_n:
            return candidates

        # Apply reranker
        try:
            from retrieval.reranker import RerankerManager

            embedding_model, _ = SearchService._get_embedding_model(knowledge_ids, workspace_id)
            reranked = RerankerManager.rerank(
                query_text=query_text,
                candidates=candidates,
                top_k=top_n,
                embedding_model=embedding_model,
            )
            return reranked
        except Exception:
            logger.warning("Reranker failed, returning original order", exc_info=True)
            return candidates[:top_n]
