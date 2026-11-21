"""Merge database translations into Django's runtime gettext catalog.

Django resolves ``_( )`` through a per-language ``DjangoTranslation`` whose
``_catalog`` maps message keys to translated strings; those objects are built
on demand and cached in ``django.utils.translation.trans_real._translations``.

We wrap the builder so that, *after* Django assembles a language's catalog from
its usual sources (the committed ``django.po``/``.mo`` files, Django's own
bundled strings, allauth, …), the active :class:`~dbi18n.models.Translation`
rows are layered on top.  Database entries therefore win, and any message
without a DB row falls through to Django's own catalog.

For plain strings a single :class:`~dbi18n.models.Translation` row at
``plural_index=0`` sets the plain catalog key.  For pluralized strings (those
whose :class:`~dbi18n.models.SourceString` has ``msgid_plural``) each row
``(msgid, plural_index)`` sets a tuple key ``(msgid, i)`` — Django's
``ngettext`` resolves these via the catalog's plural function — plus the plain
key from form 0 (mirroring GNU ``.mo`` parsing so a bare ``gettext()`` on a
pluralized msgid still resolves to the singular form).

The DB rows are layered on as their own sub-catalog inside Django's
``TranslationCatalog``, carrying the language's plural function (the same
``Plural-Forms`` the admin and export use, via
:func:`dbi18n.pofiles.plural_forms_header`).  This is essential for plurals:
``TranslationCatalog`` keeps one plural function *per* sub-catalog and, in
``ngettext``, resolves ``(msgid, plural(n))`` against each in turn.  Spanish,
for instance, ships ``nplurals=3`` at runtime, so ``plural(5) == 2``; our rows
must be indexed under that same rule or the lookup would miss.  Giving the DB
overlay its own sub-catalog with the matching plural function keeps runtime
resolution, the admin form count, and export all consistent, regardless of
which plural rule the base catalog Django assembled happens to carry.

Because catalogs are cached per process, edits propagate two ways:

* immediately in the editing process, via a ``post_save``/``post_delete``
  signal that calls :func:`reset` (see :mod:`dbi18n.signals`);
* within ``DBI18N_RELOAD_SECONDS`` in every other process, via
  :func:`refresh_if_stale` (called once per request by the middleware). This
  time-based reload needs no shared cache, so it works with the default
  per-process ``LocMemCache``.
"""

from __future__ import annotations

import gettext as gettext_module
import re
import time

from django.conf import settings
from django.db import DatabaseError
from django.utils import translation
from django.utils.translation import trans_real

# gettext separates a message's context from its id with this byte; pgettext
# looks the combined key up in the same catalog dict.
_CONTEXT_SEPARATOR = "\x04"

_original_translation = None
_built_at = 0.0


def install() -> None:
    """Patch ``trans_real.translation`` to merge DB rows into each catalog.

    Idempotent: safe to call more than once (e.g. across test app reloads).
    """
    global _original_translation
    if _original_translation is not None:
        return
    _original_translation = trans_real.translation
    trans_real.translation = _translation_with_db


def _translation_with_db(language):
    trans = _original_translation(language)
    if not getattr(trans, "_dbi18n_merged", False):
        _merge(trans, language)
        trans._dbi18n_merged = True
    return trans


def _merge(trans, language: str) -> None:
    from .models import Translation

    try:
        rows = list(
            Translation.objects.filter(language=language)
            .exclude(msgstr="")
            .select_related("source")
            .order_by("source_id", "plural_index")
            .values_list(
                "source__context",
                "source__msgid",
                "source__msgid_plural",
                "plural_index",
                "msgstr",
            )
        )
    except DatabaseError:
        # The table may not exist yet (e.g. a translation is resolved during
        # `migrate`). Leave the shipped catalog untouched.
        return

    if not rows:
        return

    db_catalog: dict = {}
    for context, msgid, msgid_plural, plural_index, msgstr in rows:
        plain_key = f"{context}{_CONTEXT_SEPARATOR}{msgid}" if context else msgid

        if msgid_plural:
            # Pluralized source: write a tuple key per form. ngettext resolves
            # (msgid, plural(n)) against this sub-catalog's plural function.
            db_catalog[(plain_key, plural_index)] = msgstr
            # Form 0 also populates the plain key so bare gettext() on a
            # pluralized msgid resolves to the singular form (mirrors .mo).
            if plural_index == 0:
                db_catalog[plain_key] = msgstr
        else:
            # Plain source: a single row at index 0 maps the plain key.
            db_catalog[plain_key] = msgstr

    _prepend_catalog(trans, db_catalog, _plural_func(language))


def _prepend_catalog(trans, db_catalog: dict, plural_func) -> None:
    """Layer ``db_catalog`` on top of Django's assembled catalog.

    Django's ``TranslationCatalog`` holds a list of sub-catalogs, each paired
    with its own plural function; lookups (plain and plural) search them in
    order. Prepending the DB rows as a leading sub-catalog with the language's
    plural function makes them win over the committed files while resolving
    plural indices under the correct rule. Falls back to a plain merge if the
    catalog is not a ``TranslationCatalog`` (older/newer Django internals).
    """
    catalog = trans._catalog
    catalogs = getattr(catalog, "_catalogs", None)
    plurals = getattr(catalog, "_plurals", None)
    if isinstance(catalogs, list) and isinstance(plurals, list):
        catalogs.insert(0, db_catalog)
        plurals.insert(0, plural_func)
    else:  # pragma: no cover — defensive against internal API changes.
        for key, value in db_catalog.items():
            catalog[key] = value


def _plural_func(language: str):
    """Compile the plural function for *language* from its ``Plural-Forms``.

    Reuses :func:`dbi18n.pofiles.plural_forms_header` — the same source the
    admin form count and export rely on — so the index scheme DB rows are
    authored under matches how ``ngettext`` resolves them at runtime.
    """
    default = lambda n: int(n != 1)  # noqa: E731 — Germanic fallback.
    try:
        from .pofiles import plural_forms_header

        header = plural_forms_header(language)
    except Exception:
        return default
    match = re.search(r"\bplural\s*=\s*([^;]+)", header)
    if not match:
        return default
    try:
        return gettext_module.c2py(match.group(1).strip())
    except Exception:
        return default


def file_value(
    language: str, context: str, msgid: str, plural_index: int | None = None
) -> str | None:
    """Return the value the committed ``.mo`` catalog has for a key, or None.

    Uses the *unpatched* translation builder so the DB overlay is bypassed —
    this is the "committed message value" used by the admin status computation
    and the prune logic. Pass ``plural_index`` to read a specific plural form
    (the catalog keys those as ``(msgid, index)`` tuples).
    """
    if _original_translation is None:
        return None
    try:
        trans = _original_translation(language)
    except Exception:
        return None
    key = f"{context}{_CONTEXT_SEPARATOR}{msgid}" if context else msgid
    if plural_index is not None:
        return trans._catalog.get((key, plural_index))
    value = trans._catalog.get(key)
    # A fallback translation object (GNUTranslations chain) may return the
    # msgid itself; treat that as "not translated in the file catalog".
    if value is None or value == msgid:
        return None
    return value


def reset() -> None:
    """Forget built catalogs so the next lookup rebuilds them from the DB."""
    global _built_at
    trans_real._translations.clear()
    trans_real._default = None
    _built_at = time.monotonic()


def refresh_if_stale() -> None:
    """Rebuild catalogs periodically so edits in other processes propagate."""
    reload_seconds = getattr(settings, "DBI18N_RELOAD_SECONDS", 30)
    if time.monotonic() - _built_at < reload_seconds:
        return
    reset()
    # Re-activate the current language so this request already sees fresh data.
    language = translation.get_language()
    if language:
        translation.activate(language)
