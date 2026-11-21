from django.apps import AppConfig


class DbI18nConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "dbi18n"
    verbose_name = "Database translations"

    def ready(self) -> None:
        from . import catalog, signals

        catalog.install()
        signals.connect()
        self._connect_post_migrate()

    def _connect_post_migrate(self) -> None:
        from django.db.models.signals import post_migrate

        post_migrate.connect(_sync_on_migrate, sender=self, dispatch_uid="dbi18n_sync_on_migrate")


def _sync_on_migrate(sender, **kwargs) -> None:
    """Run i18n_sync after every migrate so the live universe stays current."""
    from .pofiles import sync_source_strings

    sync_source_strings(stdout=None)
