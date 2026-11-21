"""The database-backed translation catalog.

Three models:

- :class:`SourceString` — the universe of translatable strings, mirrored from
  the committed ``django.po`` files by ``i18n_sync``.
- :class:`Translation` — one ``msgstr`` form for a given source string,
  language, and gettext plural index. DB rows win over the file catalog at
  runtime (see :mod:`dbi18n.catalog`), giving translators live feedback.
- :class:`SyncState` — a singleton that records the catalog-file fingerprint
  from the last sync; used by the admin to decide whether the Sync button is
  relevant.
"""

from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _


class SourceString(models.Model):
    """A translatable string extracted from the committed ``django.po`` files."""

    context = models.CharField(
        _("context"),
        max_length=255,
        blank=True,
        default="",
        help_text=_("The pgettext context, if any; blank for plain gettext."),
    )
    msgid = models.TextField(_("source string"))
    #: Non-null only for strings marked with ngettext; holds the plural form of
    #: the source (e.g. "%(count)d items").
    msgid_plural = models.TextField(_("plural source string"), blank=True, default="")
    #: Set by i18n_sync when a string has vanished from every committed .po
    #: file.  Stale entries are pruned by the admin prune action.
    is_stale = models.BooleanField(_("stale"), default=False, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _("source string")
        verbose_name_plural = _("source strings")
        ordering = ["msgid", "context"]
        constraints = [
            models.UniqueConstraint(
                fields=["context", "msgid"],
                name="dbi18n_unique_context_msgid",
            ),
        ]

    @property
    def is_plural(self) -> bool:
        return bool(self.msgid_plural)

    def __str__(self) -> str:
        if self.context:
            return f"[{self.context}] {self.msgid[:60]}"
        return self.msgid[:60]


class Translation(models.Model):
    """One msgstr form for a source string, language, and plural index.

    Plain (non-plural) strings use a single row with ``plural_index=0``.
    Pluralized strings (SourceString with ``msgid_plural``) get one row per
    gettext plural form for each language; the index is the output of the
    language's ``Plural-Forms`` expression, *not* a simple "n==1" flag.
    """

    source = models.ForeignKey(
        SourceString,
        on_delete=models.CASCADE,
        related_name="translations",
        verbose_name=_("source string"),
    )
    language = models.CharField(_("language"), max_length=15, db_index=True)
    #: gettext plural form index (0 for singular / plain; 1+ for plural forms).
    plural_index = models.PositiveSmallIntegerField(_("plural index"), default=0)
    #: The translated text.  Blank means "fall back to the file catalog."
    msgstr = models.TextField(_("translation"), blank=True)
    updated_at = models.DateTimeField(default=timezone.now)

    class Meta:
        verbose_name = _("translation")
        verbose_name_plural = _("translations")
        ordering = ["language", "source__msgid", "plural_index"]
        constraints = [
            models.UniqueConstraint(
                fields=["source", "language", "plural_index"],
                name="dbi18n_unique_source_language_plural_index",
            ),
        ]

    def save(self, *args, **kwargs):
        self.updated_at = timezone.now()
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        return f"[{self.language}:{self.plural_index}] {self.source}"


class SyncState(models.Model):
    """Singleton row tracking when the SourceString universe was last synced.

    The ``fingerprint`` is a string of ``"<path>:<mtime>:<size>"`` entries
    (sorted, newline-separated) for every committed ``django.po`` file found at
    sync time.  The admin re-stats those files on each changelist load and
    compares with the stored fingerprint — cheap file-stat only, no .po parsing.
    """

    fingerprint = models.TextField(default="")
    synced_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = _("sync state")

    @classmethod
    def get(cls) -> "SyncState":
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj
