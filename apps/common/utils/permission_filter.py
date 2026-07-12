# coding=utf-8
"""
Document-level permission filter for search results.
Filters out paragraphs from documents the user shouldn't access.
"""
from typing import List
from django.db.models import QuerySet


class PermissionFilter:
    """Post-search permission filter for document-level access control.

    Unlike workspace-level isolation (which filters knowledge_id_list),
    this provides finer-grained control: two users in the same workspace
    can see different documents within the same knowledge base.

    Usage:
        filtered = PermissionFilter.filter_paragraphs(
            paragraph_list,
            user_id="user-123",
            role="editor",
        )
    """

    @staticmethod
    def filter_paragraphs(
        paragraph_list: List[dict],
        user_id: str = None,
        role: str = "viewer",
    ) -> List[dict]:
        """Filter paragraph search results by document access permissions.

        Args:
            paragraph_list: Search results from vector/keyword search.
            user_id: Current user ID (None = anonymous/public documents only).
            role: User role (admin/editor/viewer). Admins see all.

        Returns:
            Filtered paragraph list.
        """
        if not paragraph_list or role == "admin":
            return paragraph_list

        from knowledge.models import Document

        # Get document IDs from paragraph results
        doc_ids = list(set(p.get("document_id") for p in paragraph_list if p.get("document_id")))

        if not doc_ids:
            return paragraph_list

        # Filter to authorized documents
        qs = Document.objects.filter(id__in=doc_ids, is_active=True)
        if user_id:
            # Authenticated users: see own docs + public docs
            qs = qs.filter(user_id__in=[user_id, None])
        else:
            # Anonymous: only public docs
            qs = qs.filter(user_id__isnull=True)

        authorized_ids = set(str(d.id) for d in qs)

        return [p for p in paragraph_list if p.get("document_id") in authorized_ids]

    @staticmethod
    def get_authorized_document_ids(
        knowledge_id: str, user_id: str = None, role: str = "viewer"
    ) -> List[str]:
        """Get list of document IDs the user can access within a knowledge base."""
        from knowledge.models import Document

        if role == "admin":
            return list(
                Document.objects.filter(knowledge_id=knowledge_id, is_active=True).values_list("id", flat=True)
            )

        qs = Document.objects.filter(knowledge_id=knowledge_id, is_active=True)
        if user_id:
            qs = qs.filter(user_id__in=[user_id, None])
        else:
            qs = qs.filter(user_id__isnull=True)

        return [str(d) for d in qs.values_list("id", flat=True)]
