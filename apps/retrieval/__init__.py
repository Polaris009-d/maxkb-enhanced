# coding=utf-8
"""
Multi-strategy retrieval: vector, keyword, hybrid, reranker.

Supports pgvector (dense), BM25/tsquery (sparse), RRF fusion, and
Cross-Encoder re-ranking with embedding fallback.
"""
