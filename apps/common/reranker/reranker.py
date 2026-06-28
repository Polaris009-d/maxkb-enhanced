# coding=utf-8
"""
Reranker for RAG retrieval results.

Uses a Cross-Encoder model to compute fine-grained relevance scores
between the query and each retrieved passage, then re-ranks the results.
Falls back to embedding-based re-ranking if no Cross-Encoder is available.
"""
import logging
from typing import List

import numpy as np

logger = logging.getLogger("maxkb.reranker")


class RerankerManager:
    """Re-ranks search results using Cross-Encoder or embedding similarity.

    Takes the top-N results from the vector/keyword search and re-scores
    each candidate against the query using a more precise model, then
    returns the top-K results.

    Usage:
        reranked = RerankerManager.rerank(
            query_text="奖学金如何申请",
            candidates=[{"paragraph_id": "...", "content": "...", "score": 0.85}, ...],
            top_k=5,
            embedding_model=model,  # fallback
        )
    """

    _cross_encoder = None
    _cross_encoder_model_name = "BAAI/bge-reranker-base"

    @classmethod
    def _get_cross_encoder(cls):
        """Lazy-load the Cross-Encoder model."""
        if cls._cross_encoder is None:
            try:
                from sentence_transformers import CrossEncoder

                cls._cross_encoder = CrossEncoder(cls._cross_encoder_model_name)
                logger.info(f"Loaded CrossEncoder: {cls._cross_encoder_model_name}")
            except Exception as e:
                logger.warning(f"Failed to load CrossEncoder: {e}, will use embedding fallback")
                cls._cross_encoder = False  # Mark as unavailable
        return cls._cross_encoder if cls._cross_encoder is not False else None

    @classmethod
    def rerank_cross_encoder(
        cls,
        query_text: str,
        candidates: List[dict],
        top_k: int = 5,
    ) -> List[dict]:
        """Re-rank using Cross-Encoder model."""
        model = cls._get_cross_encoder()
        if model is None:
            return None

        pairs = [(query_text, c["content"]) for c in candidates if c.get("content")]
        if not pairs:
            return candidates[:top_k]

        scores = model.predict(pairs, show_progress_bar=False)
        # Normalize scores to 0-1 range
        if len(scores) > 0:
            score_min, score_max = np.min(scores), np.max(scores)
            if score_max > score_min:
                scores = (scores - score_min) / (score_max - score_min)

        for i, candidate in enumerate(candidates):
            if i < len(scores):
                candidate["rerank_score"] = float(scores[i])

        candidates.sort(key=lambda x: x.get("rerank_score", 0), reverse=True)
        return candidates[:top_k]

    @classmethod
    def rerank_embedding_fallback(
        cls,
        query_text: str,
        candidates: List[dict],
        top_k: int,
        embedding_model,
    ) -> List[dict]:
        """Re-rank using query-document embedding cosine similarity."""
        if embedding_model is None:
            return candidates[:top_k]

        try:
            query_emb = embedding_model.embed_query(query_text)
            texts = [c.get("content", "") for c in candidates]
            doc_embs = embedding_model.embed_documents(texts)

            query_arr = np.array(query_emb, dtype=np.float64)
            for i, doc_emb in enumerate(doc_embs):
                doc_arr = np.array(doc_emb, dtype=np.float64)
                dot = np.dot(query_arr, doc_arr)
                norm_q = np.linalg.norm(query_arr)
                norm_d = np.linalg.norm(doc_arr)
                if norm_q > 0 and norm_d > 0:
                    candidates[i]["rerank_score"] = float(dot / (norm_q * norm_d))
                else:
                    candidates[i]["rerank_score"] = 0.0

            candidates.sort(key=lambda x: x.get("rerank_score", 0), reverse=True)
            return candidates[:top_k]
        except Exception as e:
            logger.warning(f"Embedding rerank failed: {e}")
            return candidates[:top_k]

    @classmethod
    def rerank(
        cls,
        query_text: str,
        candidates: List[dict],
        top_k: int = 5,
        embedding_model=None,
        candidate_top_n: int = 20,
    ) -> List[dict]:
        """Main entry point: re-rank search results.

        Args:
            query_text: User's question.
            candidates: List of {paragraph_id, content, comprehensive_score, ...}
            top_k: Number of results to return after re-ranking.
            embedding_model: Embedding model for fallback.
            candidate_top_n: Take top N candidates for re-ranking.

        Returns:
            Re-ranked candidate list, limited to top_k.
        """
        if not candidates:
            return []

        # Only re-rank the top N candidates
        candidates_to_rerank = candidates[:candidate_top_n]

        # Try Cross-Encoder first (more accurate)
        result = cls.rerank_cross_encoder(query_text, candidates_to_rerank, top_k)
        if result is not None:
            logger.debug(f"Cross-Encoder rerank: {len(candidates)} -> {len(result)}")
            return result

        # Fallback to embedding similarity
        result = cls.rerank_embedding_fallback(query_text, candidates_to_rerank, top_k, embedding_model)
        logger.debug(f"Embedding fallback rerank: {len(candidates)} -> {len(result)}")
        return result
