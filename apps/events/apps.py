# coding=utf-8
"""
Django app configuration for the event bus.
Registers default event handlers on startup.
"""
from django.apps import AppConfig


class EventsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "events"

    def ready(self):
        # Import handlers to register them with the EventBus
        try:
            import events.handlers  # noqa: F401
        except ImportError:
            pass
