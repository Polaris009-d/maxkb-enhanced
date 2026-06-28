# coding=utf-8
"""
Helper for publishing document indexing progress via Django Channels.
"""
import asyncio
import logging

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer

logger = logging.getLogger("maxkb.websocket")


class IndexProgressPublisher:
    """Publishes indexing progress updates to WebSocket clients via Channels.

    Usage::

        IndexProgressPublisher.publish_progress(
            document_id="abc123",
            stage="chunk",
            status="in_progress",
            percentage=60,
            message="Processing 120/200 chunks",
        )
    """

    @staticmethod
    def publish_progress(
        document_id: str,
        stage: str,
        status: str,
        percentage: int = 0,
        message: str = "",
    ):
        """Publish a progress update to the document's WebSocket group.

        Args:
            document_id: The document being processed.
            stage: One of 'parse', 'chunk', 'embed', 'store'.
            status: One of 'started', 'in_progress', 'completed', 'failed'.
            percentage: Progress percentage (0-100) for this stage.
            message: Human-readable status message.
        """
        try:
            channel_layer = get_channel_layer()
            if channel_layer is None:
                return  # Channels not configured (e.g. in management commands)

            group_name = f"document_progress_{document_id}"
            async_to_sync(channel_layer.group_send)(
                group_name,
                {
                    "type": "progress_message",
                    "document_id": str(document_id),
                    "stage": stage,
                    "status": status,
                    "percentage": percentage,
                    "message": message,
                },
            )
        except Exception as e:
            logger.warning(f"Failed to publish progress for doc {document_id}: {e}")
