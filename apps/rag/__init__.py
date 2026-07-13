# coding=utf-8
"""
RAG (Retrieval-Augmented Generation) pipeline.

Orchestrates the full RAG flow: query → retrieve → rerank → generate.

For now, step implementations live in application.chat_pipeline.step.
New RAG components should be developed here and migrated gradually.
"""
