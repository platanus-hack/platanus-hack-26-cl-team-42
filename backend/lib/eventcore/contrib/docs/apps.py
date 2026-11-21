from django.apps import AppConfig


class EventcoreDocsConfig(AppConfig):
    """Optional UI + templates for the eventcore documentation graph."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "eventcore.contrib.docs"
    label = "eventcore_docs"
    verbose_name = "Eventcore docs"
