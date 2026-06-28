# coding=utf-8
"""
WebSocket URL routing for Django Channels.
"""
from django.urls import re_path

from .consumers import DocumentProgressConsumer

websocket_urlpatterns = [
    re_path(r"ws/document/(?P<document_id>[^/]+)/progress/$", DocumentProgressConsumer.as_asgi()),
]
