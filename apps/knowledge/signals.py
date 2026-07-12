# coding=utf-8
"""
Signals: auto re-embedding on model change, document version management.
"""
from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver
from knowledge.models import Knowledge

# Module-level cache to bridge pre_save → post_save for change detection.
# Key: Knowledge instance id, Value: old embedding_model_id (or None).
_old_embedding_model_ids: dict = {}


@receiver(pre_save, sender=Knowledge)
def _cache_old_embedding_model(sender, instance, **kwargs):
    """pre_save: snapshot the current embedding_model_id before the save overwrites it.

    Only relevant for updates (instance.pk already exists).  For new records
    there is no "old" value to compare against.
    """
    if not instance.pk:
        return
    try:
        old = Knowledge.objects.only('embedding_model_id').get(id=instance.id)
        _old_embedding_model_ids[instance.id] = old.embedding_model_id
    except Knowledge.DoesNotExist:
        pass


@receiver(post_save, sender=Knowledge)
def on_knowledge_embedding_model_changed(sender, instance, **kwargs):
    """post_save: if the embedding model was changed, re-embed all active documents.

    Compares the *new* value (from the just-saved instance) against the
    *old* value captured in pre_save.  On a genuine change every active
    paragraph is reset to PENDING and the Celery embedding tasks are
    re-dispatched.
    """
    old_model_id = _old_embedding_model_ids.pop(instance.id, None)

    # Newly-created knowledge base → nothing to re-embed yet.
    if old_model_id is None:
        return

    # Model unchanged → nothing to do.
    if old_model_id == instance.embedding_model_id:
        return

    # Model removed (set to None) → no re-embedding needed.
    if not instance.embedding_model_id:
        return

    # --- Model changed: re-embed all active documents ---
    from django.db.models import F, Value
    from django.db.models.functions import Substr, Concat
    from knowledge.models import Document, Paragraph
    from knowledge.task.embedding import embedding_by_document

    documents = Document.objects.filter(knowledge_id=instance.id, is_active=True)
    for doc in documents:
        # Reset paragraphs to PENDING state (first char of status string)
        Paragraph.objects.filter(document_id=doc.id).update(
            status=Concat(Value('0'), Substr(F('status'), 2))
        )
        embedding_by_document.delay(str(doc.id), str(instance.embedding_model_id))
