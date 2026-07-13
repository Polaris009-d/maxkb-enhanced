# coding=utf-8
"""
Document ingestion pipeline service.

Orchestrates the full ingestion flow:
    1. Parse (PDF/DOCX/HTML)
    2. OCR fallback for scanned documents
    3. Table extraction
    4. Smart chunking

Usage:
    from ingestion.services.pipeline import ingest_document

    result = ingest_document(
        file=uploaded_file,
        pattern_list=None,
        with_filter=True,
        limit=5000,
    )
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from ingestion.chunker import SplitModel, smart_split_paragraph
from ingestion.parser.pdf import default_pattern_list
from ingestion.extractor.table import TableExtractor
from ingestion.ocr.baidu import is_ocr_needed, ocr_image

logger = logging.getLogger("maxkb.ingestion")


class DocumentIngestionResult:
    """Result of document ingestion pipeline."""

    def __init__(
        self,
        file_name: str,
        content: Any,
        table_data: Optional[Dict] = None,
        ocr_applied: bool = False,
        pdfplumber_fallback: bool = False,
    ):
        self.file_name = file_name
        self.content = content
        self.table_data = table_data or {"tables": [], "table_count": 0}
        self.ocr_applied = ocr_applied
        self.pdfplumber_fallback = pdfplumber_fallback

    def to_dict(self) -> Dict:
        return {
            "name": self.file_name,
            "content": self.content,
            "meta": self.table_data,
        }


def build_split_model(
    pattern_list: Optional[List] = None,
    with_filter: bool = True,
    limit: int = 5000,
) -> SplitModel:
    """Build a SplitModel instance from parameters.

    Args:
        pattern_list: Custom split patterns, or None for defaults.
        with_filter: Whether to apply special character filtering.
        limit: Maximum characters per chunk.

    Returns:
        Configured SplitModel instance.
    """
    if pattern_list:
        return SplitModel(pattern_list, with_filter, limit)
    return SplitModel(default_pattern_list, with_filter=with_filter, limit=limit)


def chunk_text(
    content: str,
    pattern_list: Optional[List] = None,
    with_filter: bool = True,
    limit: int = 5000,
) -> List[str]:
    """Split text into chunks using the configured SplitModel.

    Args:
        content: Raw text to split.
        pattern_list: Custom split patterns.
        with_filter: Apply special character filtering.
        limit: Max chars per chunk.

    Returns:
        List of chunk strings.
    """
    model = build_split_model(pattern_list, with_filter, limit)
    return model.parse(content)


def extract_tables(file_bytes: bytes, file_path: Optional[str] = None) -> Dict:
    """Extract structured tables from a document.

    Args:
        file_bytes: Raw file bytes.
        file_path: Optional file path (needed for camelot fallback).

    Returns:
        Dict with keys: tables, table_count, method.
    """
    return TableExtractor.extract_tables(file_bytes, file_path)
