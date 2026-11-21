from django.apps import AppConfig


class DemoConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.demo"

    def ready(self):
        import eventcore

        # Import commands so they self-register into the eventcore command
        # registry.  Previously this happened as a side-effect of api.py
        # importing them; now that api.py is read-only, we do it explicitly.
        from . import commands  # noqa: F401
        from .events import OrderEvent
        from .policies import announce_order_event

        eventcore.on(OrderEvent, announce_order_event)
