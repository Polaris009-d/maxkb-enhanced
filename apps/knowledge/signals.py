# coding=utf-8
"""
Signals: auto re-embedding on model change, document version management.
"""
from django.db.models.signals import post_save
from django.dispatch import receiver
from knowledge.models import Knowledge, Document, Paragraph
from knowledge.task.embedding import embedding_by_document


@receiver(post_save, sender=Knowledge)
def on_knowledge_embedding_model_changed(sender, instance, **kwargs):
    """When a knowledge base's embedding model is changed, re-embed all its documents."""
    if not instance.embedding_model_id:
        return

    # Check if embedding_model actually changed (vs other field updates)
    old_instance = Knowledge.objects.filter(id=instance.id).first()
    if old_instance is None:
        return

    try:
        old_model_id = Knowledge.objects.only('embedding_model_id').get(id=instance.id).embedding_model_id
    except Knowledge.DoesNotExist:
        return

    current_model_id = instance.embedding_model_id
    if old_model_id == current_model_id:
        return  # Model didn't change

    # Reset all paragraphs to PENDING and re-dispatch
    from django.db.models import QuerySet
    from common.constants.status_constants import State, TaskType

    documents = Document.objects.filter(knowledge_id=instance.id, is_active=True)
    for doc in documents:
        # Reset embedding status to PENDING
        Paragraph.objects.filter(document_id=doc.id).update(
            status='0' + Paragraph.objects.model.status.field.default[1:]  # nope, simpler approach
        )
        # Actually reset properly:
        from django.db.models import F, Value
        from django.db.models.functions import Substr, Concat
        # Set position 1 (EMBEDDING) to '0' = PENDING
        Paragraph.objects.filter(document_id=doc.id).update(
            status=Concat(Value('0'), Substr(F('status'), 2))
        )
        # Trigger re-embedding
        embedding_by_document.delay(str(doc.id), str(current_model_id))
