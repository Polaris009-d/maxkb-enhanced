# coding=utf-8
"""
Semantic cache manager for LLM response caching.
Uses Redis to store question embeddings and cached answers,
retrieving them by cosine similarity threshold.
"""

import hashlib
import json
import logging

import django_redis
import numpy as np

from django.utils.translation import gettext_lazy as _

logger = logging.getLogger("maxkb.semantic_cache")


class SemanticCacheManager:
    """Manages semantic caching of LLM responses in Redis.

    Caches (question_embedding, answer_text, token_counts) keyed by
    application_id. On lookup, computes cosine similarity between the
    new question embedding and all cached embeddings for that application.
    Returns the cached answer if similarity >= threshold (default 0.92).
    """

    CACHE_KEY_PREFIX = "semantic_cache"
    DEFAULT_SIMILARITY_THRESHOLD = 0.92
    DEFAULT_TTL = 86400  # 24 hours

    @staticmethod
    def _get_redis_client():
        """Get the default Redis connection (already configured via django-redis)."""
        return django_redis.get_redis_connection("default")

    @staticmethod
    def _get_cache_key(application_id: str, hash_id: str) -> str:
        return f"{SemanticCacheManager.CACHE_KEY_PREFIX}:{application_id}:{hash_id}"

    @staticmethod
    def _get_index_key(application_id: str) -> str:
        return f"{SemanticCacheManager.CACHE_KEY_PREFIX}:index:{application_id}"

    @staticmethod
    def compute_embedding(question_text: str, model_instance) -> list:
        """Compute embedding vector for a question text.

        Args:
            question_text: The user's question.
            model_instance: An embedding model instance with embed_query() method.

        Returns:
            List of floats representing the embedding vector.
        """
        if model_instance is None:
            return None
        try:
            embedding = model_instance.embed_query(question_text)
            return embedding
        except Exception as e:
            logger.warning(f"Failed to compute embedding for cache: {e}")
            return None

    @staticmethod
    def cosine_similarity(a: list, b: list) -> float:
        """Compute cosine similarity between two vectors."""
        if a is None or b is None or len(a) == 0 or len(b) == 0:
            return 0.0
        a_arr = np.array(a, dtype=np.float64)
        b_arr = np.array(b, dtype=np.float64)
        dot = np.dot(a_arr, b_arr)
        norm_a = np.linalg.norm(a_arr)
        norm_b = np.linalg.norm(b_arr)
        if norm_a == 0 or norm_b == 0:
            return 0.0
        return float(dot / (norm_a * norm_b))

    @staticmethod
    def search(
        question_text: str,
        application_id: str,
        model_instance,
        similarity_threshold: float = None,
    ) -> dict:
        """Search Redis for a semantically similar cached answer.

        Args:
            question_text: The user's question.
            application_id: The application ID (used as cache namespace).
            model_instance: The embedding model instance for computing vectors.
            similarity_threshold: Minimum cosine similarity (default 0.92).

        Returns:
            dict with keys (answer_text, message_tokens, answer_tokens, problem_text)
            if a cache hit is found, or None on miss.
        """
        if similarity_threshold is None:
            similarity_threshold = SemanticCacheManager.DEFAULT_SIMILARITY_THRESHOLD

        redis_client = SemanticCacheManager._get_redis_client()
        index_key = SemanticCacheManager._get_index_key(application_id)

        # Get all cached hash IDs for this application
        hash_ids = redis_client.smembers(index_key)
        if not hash_ids:
            return None

        # Compute embedding for the new question
        query_embedding = SemanticCacheManager.compute_embedding(question_text, model_instance)
        if query_embedding is None:
            return None

        # Iterate through cached entries and find the best match
        best_similarity = 0.0
        best_entry = None

        for hash_id in hash_ids:
            hash_id_str = hash_id.decode("utf-8") if isinstance(hash_id, bytes) else str(hash_id)
            cache_key = SemanticCacheManager._get_cache_key(application_id, hash_id_str)
            cached_data = redis_client.hgetall(cache_key)
            if not cached_data:
                # Clean up stale index entry
                redis_client.srem(index_key, hash_id)
                continue

            try:
                # Decode and parse cached embedding
                cached_embedding_str = (
                    cached_data[b"embedding"].decode("utf-8")
                    if isinstance(cached_data.get(b"embedding"), bytes)
                    else cached_data.get("embedding", "")
                )
                if not cached_embedding_str:
                    continue

                cached_embedding = json.loads(cached_embedding_str)
                sim = SemanticCacheManager.cosine_similarity(query_embedding, cached_embedding)

                if sim > best_similarity:
                    best_similarity = sim
                    problem_text = (
                        cached_data[b"problem_text"].decode("utf-8")
                        if isinstance(cached_data.get(b"problem_text"), bytes)
                        else cached_data.get("problem_text", "")
                    )
                    answer_text = (
                        cached_data[b"answer_text"].decode("utf-8")
                        if isinstance(cached_data.get(b"answer_text"), bytes)
                        else cached_data.get("answer_text", "")
                    )
                    msg_tokens = int(
                        cached_data[b"message_tokens"].decode("utf-8")
                        if isinstance(cached_data.get(b"message_tokens"), bytes)
                        else cached_data.get("message_tokens", "0")
                    )
                    ans_tokens = int(
                        cached_data[b"answer_tokens"].decode("utf-8")
                        if isinstance(cached_data.get(b"answer_tokens"), bytes)
                        else cached_data.get("answer_tokens", "0")
                    )
                    best_entry = {
                        "answer_text": answer_text,
                        "message_tokens": msg_tokens,
                        "answer_tokens": ans_tokens,
                        "problem_text": problem_text,
                        "similarity": best_similarity,
                    }
            except (json.JSONDecodeError, ValueError, KeyError) as e:
                logger.warning(f"Failed to parse cached entry {hash_id_str}: {e}")
                continue

        if best_similarity >= similarity_threshold:
            logger.info(
                f"Semantic cache HIT for app={application_id}, "
                f"similarity={best_similarity:.4f}, "
                f'question="{question_text[:50]}..."'
            )
            return best_entry

        logger.debug(
            f"Semantic cache MISS for app={application_id}, "
            f"best_similarity={best_similarity:.4f}, "
            f'threshold={similarity_threshold}'
        )
        return None

    @staticmethod
    def cache(
        problem_text: str,
        answer_text: str,
        message_tokens: int,
        answer_tokens: int,
        embedding: list,
        application_id: str,
        ttl: int = None,
    ):
        """Store a new entry in the semantic cache.

        Args:
            problem_text: The original user question.
            answer_text: The LLM's complete response.
            message_tokens: Input token count.
            answer_tokens: Output token count.
            embedding: The embedding vector for the question.
            application_id: The application ID.
            ttl: Time-to-live in seconds (default 86400 = 24h).
        """
        if ttl is None:
            ttl = SemanticCacheManager.DEFAULT_TTL
        if embedding is None or not answer_text:
            return

        redis_client = SemanticCacheManager._get_redis_client()
        hash_id = hashlib.md5(problem_text.encode("utf-8")).hexdigest()[:16]
        cache_key = SemanticCacheManager._get_cache_key(application_id, hash_id)
        index_key = SemanticCacheManager._get_index_key(application_id)

        cache_data = {
            "embedding": json.dumps(embedding),
            "answer_text": answer_text,
            "message_tokens": str(message_tokens),
            "answer_tokens": str(answer_tokens),
            "problem_text": problem_text,
        }

        redis_client.hset(cache_key, mapping=cache_data)
        redis_client.expire(cache_key, ttl)
        redis_client.sadd(index_key, hash_id)
        redis_client.expire(index_key, ttl)

        logger.info(
            f"Semantic cache STORED for app={application_id}, "
            f'hash={hash_id}, question="{problem_text[:50]}..."'
        )

    @staticmethod
    def invalidate(application_id: str):
        """Invalidate (delete) all cached entries for an application.

        Call this when the application's model, knowledge base, or settings change.
        """
        redis_client = SemanticCacheManager._get_redis_client()
        index_key = SemanticCacheManager._get_index_key(application_id)
        hash_ids = redis_client.smembers(index_key)

        count = len(hash_ids)
        for hash_id in hash_ids:
            hash_id_str = hash_id.decode("utf-8") if isinstance(hash_id, bytes) else str(hash_id)
            cache_key = SemanticCacheManager._get_cache_key(application_id, hash_id_str)
            redis_client.delete(cache_key)

        redis_client.delete(index_key)
        logger.info(f"Semantic cache INVALIDATED for app={application_id}, removed {count} entries")
