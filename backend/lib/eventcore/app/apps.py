from django.apps import AppConfig


class EventcoreAppConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "eventcore.app"
    # Explicit label: the default would be the generic last component, "app".
    label = "eventcore"
    verbose_name = "Eventcore log"

    def ready(self) -> None:
        from . import subscribers

        subscribers.register()
