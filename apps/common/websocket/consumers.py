# coding=utf-8
"""
WebSocket consumers for real-time progress updates.
"""
import asyncio
import json

from channels.generic.websocket import AsyncWebsocketConsumer


class DocumentProgressConsumer(AsyncWebsocketConsumer):
    """WebSocket consumer that broadcasts document indexing progress.

    Joins a channel group named 'document_progress_{document_id}'
    and forwards progress messages to the connected WebSocket client.
    """

    async def connect(self):
        document_id = self.scope["url_route"]["kwargs"]["document_id"]
        self.group_name = f"document_progress_{document_id}"

        # Join the document-specific group
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()

    async def disconnect(self, close_code):
        # Leave the document-specific group
        if hasattr(self, "group_name"):
            await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def receive(self, text_data=None, bytes_data=None):
        # Client can send ping to keep connection alive
        pass

    async def progress_message(self, event):
        """Receive progress updates from the group and forward to WebSocket client."""
        await self.send(
            text_data=json.dumps(
                {
                    "document_id": event.get("document_id"),
                    "stage": event.get("stage"),
                    "status": event.get("status"),
                    "percentage": event.get("percentage", 0),
                    "message": event.get("message", ""),
                }
            )
        )
