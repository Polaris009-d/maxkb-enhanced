# coding=utf-8
"""
Document version management — tracks PDF updates without full re-upload.
Uses the existing Document.meta JSON field to store version history.
"""
import json
import uuid_utils.compat as uuid
from datetime import datetime
from django.db.models import F
from django.db import transaction


class DocumentVersionManager:
    """Manage document versions using Document.meta JSON field."""

    META_KEY = "__versions__"

    @classmethod
    def get_versions(cls, document):
        """Get version history from document meta."""
        meta = document.meta or {}
        return meta.get(cls.META_KEY, [])

    @classmethod
    def add_version(cls, document, file_info: dict = None):
        """Add a new version entry when document content changes.

        Args:
            document: Document instance
            file_info: dict with keys like {'file_hash': '...', 'file_size': ...}
        """
        meta = document.meta or {}
        versions = meta.get(cls.META_KEY, [])

        new_version = {
            "version_id": str(uuid.uuid7()),
            "created_at": datetime.now().isoformat(),
            "file_hash": file_info.get("file_hash", "") if file_info else "",
            "file_size": file_info.get("file_size", 0) if file_info else 0,
            "paragraph_count": document.paragraph_set.count(),
            "char_length": document.char_length,
        }
        versions.append(new_version)

        # Keep last 10 versions
        if len(versions) > 10:
            versions = versions[-10:]

        meta[cls.META_KEY] = versions
        document.meta = meta
        document.save(update_fields=["meta", "update_time"])

        return new_version

    @classmethod
    def get_latest_version(cls, document):
        versions = cls.get_versions(document)
        return versions[-1] if versions else None

    @classmethod
    def get_version_count(cls, document):
        return len(cls.get_versions(document))
