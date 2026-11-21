"""Unit tests for the dbi18n database-backed gettext catalog.

The suite covers:
- DB overlay: Translation rows win over committed .po values.
- File fallback: committed .po values serve when no DB row exists.
- Plural forms: per-index Translation rows work with ngettext.
- pgettext / context scoping.
- i18n_sync: upserting SourceStrings, stale marking, fingerprint recording.
- Prune: removes redundant Translation rows and stale SourceStrings.
- Export / Import round-trip: messages.tar.gz written and read back.
- Admin status computation.

The demo app ships a committed django.po (apps/demo/locale/es/LC_MESSAGES/)
which must be compiled to a .mo before any catalog test runs.  The session-
scoped ``compiled_mo`` fixture handles this idempotently via polib.
"""

from __future__ import annotations

import io as _io
import subprocess

import polib
import pytest
from django.utils import translation

from dbi18n import catalog as dbi18n_catalog
from dbi18n.models import SourceString, SyncState, Translation
from dbi18n.pofiles import (
    export_to_tarball,
    import_from_tarball,
    locate_po_files,
    prune,
    sync_source_strings,
)

# ---------------------------------------------------------------------------
# Session fixture: ensure .mo files are compiled
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session", autouse=True)
def compiled_mo():
    """Compile all django.po files to django.mo before any test in this session.

    Uses msgfmt (gettext) if available; falls back to polib for environments
    where msgfmt is absent.  Tolerates read-only trees (the .mo may already
    exist from an image build / entrypoint compile step).
    """
    for po_path in locate_po_files():
        mo_path = po_path.with_suffix(".mo")
        try:
            # Fast path: already compiled and up-to-date.
            if mo_path.exists() and mo_path.stat().st_mtime >= po_path.stat().st_mtime:
                continue
            # Try msgfmt first (native, handles edge cases).
            result = subprocess.run(
                ["msgfmt", "-o", str(mo_path), str(po_path)],
                capture_output=True,
            )
            if result.returncode == 0:
                continue
            # Fall back to polib.
            po = polib.pofile(str(po_path))
            po.save_as_mofile(str(mo_path))
        except (OSError, PermissionError):
            # Read-only bind mount; assume the .mo was pre-compiled.
            pass


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_source(msgid: str, context: str = "", msgid_plural: str = "") -> SourceString:
    obj, _ = SourceString.objects.get_or_create(
        context=context,
        msgid=msgid,
        defaults={"msgid_plural": msgid_plural},
    )
    return obj


def _make_translation(source: SourceString, lang: str, msgstr: str, plural_index: int = 0):
    return Translation.objects.create(
        source=source, language=lang, msgstr=msgstr, plural_index=plural_index
    )


# ---------------------------------------------------------------------------
# Basic overlay
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_file_catalog_serves_spanish_from_po():
    """Committed django.po provides Spanish translations with no DB rows."""
    dbi18n_catalog.reset()
    with translation.override("es"):
        assert translation.gettext("Pending") == "Pendiente"
    with translation.override("en"):
        assert translation.gettext("Pending") == "Pending"


@pytest.mark.django_db
def test_db_row_wins_over_file_catalog():
    """A Translation row overrides the committed .po value."""
    src = _make_source("Pending")
    _make_translation(src, "es", "Esperando")
    dbi18n_catalog.reset()
    try:
        with translation.override("es"):
            assert translation.gettext("Pending") == "Esperando"
    finally:
        dbi18n_catalog.reset()


@pytest.mark.django_db
def test_file_value_resumes_after_db_row_deleted():
    """Deleting the DB row restores the committed .po value."""
    src = _make_source("Pending")
    t = _make_translation(src, "es", "Temporal")
    dbi18n_catalog.reset()
    t.delete()
    dbi18n_catalog.reset()
    with translation.override("es"):
        assert translation.gettext("Pending") == "Pendiente"


@pytest.mark.django_db
def test_unknown_message_falls_back_to_source():
    dbi18n_catalog.reset()
    with translation.override("es"):
        assert translation.gettext("Not in the catalog") == "Not in the catalog"


@pytest.mark.django_db
def test_new_row_is_picked_up_after_invalidation():
    """Creating a row makes it resolvable immediately after catalog reset."""
    src = _make_source("Rubber duck")
    _make_translation(src, "es", "Pato de goma")
    dbi18n_catalog.reset()
    try:
        with translation.override("es"):
            assert translation.gettext("Rubber duck") == "Pato de goma"
    finally:
        dbi18n_catalog.reset()


@pytest.mark.django_db
def test_context_scoped_translations_are_independent():
    """pgettext lookups are keyed by context."""
    src_month = _make_source("May", context="month")
    src_verb = _make_source("May", context="verb")
    _make_translation(src_month, "es", "Mayo")
    _make_translation(src_verb, "es", "Poder")
    dbi18n_catalog.reset()
    try:
        with translation.override("es"):
            assert translation.pgettext("month", "May") == "Mayo"
            assert translation.pgettext("verb", "May") == "Poder"
    finally:
        dbi18n_catalog.reset()


# ---------------------------------------------------------------------------
# Plural forms
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_plural_overlay_ngettext():
    """DB plural rows work with ngettext, indexed by the language's real rule.

    Spanish ships ``nplurals=3`` at runtime (``n == 1 ? 0 : … ? 1 : 2``), so
    ``ngettext(..., 1)`` resolves form 0 and ``ngettext(..., 5)`` resolves
    form 2 — not form 1. The DB rows must be authored under that same scheme,
    and the overlay must resolve them with the matching plural function.
    """
    from dbi18n.pofiles import plural_form_count

    assert plural_form_count("es") == 3  # guards the assumption below

    src = _make_source("%(count)s item", msgid_plural="%(count)s items")
    _make_translation(src, "es", "%(count)s artículo", plural_index=0)
    _make_translation(src, "es", "%(count)s artículo (millón)", plural_index=1)
    _make_translation(src, "es", "%(count)s artículos", plural_index=2)
    dbi18n_catalog.reset()
    try:
        with translation.override("es"):
            singular = translation.ngettext("%(count)s item", "%(count)s items", 1)
            plural = translation.ngettext("%(count)s item", "%(count)s items", 5)
            assert singular == "%(count)s artículo"
            assert plural == "%(count)s artículos"
    finally:
        dbi18n_catalog.reset()


@pytest.mark.django_db
def test_plural_form_0_also_sets_plain_key():
    """bare gettext() on a pluralized msgid returns the singular (form 0) translation."""
    src = _make_source("apple", msgid_plural="apples")
    _make_translation(src, "es", "manzana", plural_index=0)
    _make_translation(src, "es", "manzanas", plural_index=1)
    dbi18n_catalog.reset()
    try:
        with translation.override("es"):
            assert translation.gettext("apple") == "manzana"
    finally:
        dbi18n_catalog.reset()


# ---------------------------------------------------------------------------
# file_value helper
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_file_value_returns_committed_po_value():
    """file_value reads the .mo catalog, bypassing any DB overlay."""
    dbi18n_catalog.reset()
    val = dbi18n_catalog.file_value("es", "", "Pending")
    assert val == "Pendiente"


@pytest.mark.django_db
def test_file_value_returns_none_for_unknown_msgid():
    dbi18n_catalog.reset()
    val = dbi18n_catalog.file_value("es", "", "Nonexistent string xyz")
    assert val is None


# ---------------------------------------------------------------------------
# i18n_sync
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_sync_creates_source_strings_from_po():
    """i18n_sync upserts SourceStrings from committed .po files."""
    SourceString.objects.all().delete()
    sync_source_strings()
    assert SourceString.objects.filter(msgid="Pending").exists()


@pytest.mark.django_db
def test_sync_records_fingerprint_in_sync_state():
    """i18n_sync writes a non-empty fingerprint to SyncState."""
    sync_source_strings()
    state = SyncState.get()
    assert state.fingerprint != ""
    assert state.synced_at is not None


@pytest.mark.django_db
def test_sync_marks_vanished_strings_stale():
    """A SourceString absent from every .po is marked stale by sync."""
    orphan = SourceString.objects.create(context="", msgid="__orphan_test__")
    sync_source_strings()
    orphan.refresh_from_db()
    assert orphan.is_stale


@pytest.mark.django_db
def test_sync_clears_stale_flag_when_string_reappears():
    """If a string is in the .po, it is NOT stale even if it was before."""
    sync_source_strings()
    src = SourceString.objects.get(msgid="Pending")
    assert not src.is_stale


# ---------------------------------------------------------------------------
# Prune
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_prune_removes_redundant_translation():
    """Prune deletes a Translation whose msgstr equals the file catalog value."""
    src = _make_source("Pending")
    t = _make_translation(src, "es", "Pendiente")  # same as the .po
    dbi18n_catalog.reset()
    t_count, _ss_count = prune()
    assert not Translation.objects.filter(pk=t.pk).exists()
    assert t_count >= 1


@pytest.mark.django_db
def test_prune_keeps_modified_translation():
    """Prune must NOT delete a Translation that differs from the file value."""
    src = _make_source("Pending")
    t = _make_translation(src, "es", "Pendiente (custom)")
    dbi18n_catalog.reset()
    prune()
    assert Translation.objects.filter(pk=t.pk).exists()


@pytest.mark.django_db
def test_prune_deletes_stale_source_strings():
    """Prune hard-deletes SourceStrings marked is_stale=True."""
    orphan = SourceString.objects.create(context="", msgid="__stale_test__", is_stale=True)
    prune()
    assert not SourceString.objects.filter(pk=orphan.pk).exists()


# ---------------------------------------------------------------------------
# Export / Import round-trip
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_export_import_roundtrip(tmp_path, settings):  # noqa: F811
    """Export writes a tarball; import merges it into LOCALE_PATHS[0]."""
    # Set LOCALE_PATHS to a temp dir so we don't modify the real tree.
    locale_root = tmp_path / "locale"
    locale_root.mkdir()
    settings.LOCALE_PATHS = [str(locale_root)]

    # Create a Translation to export.
    src = _make_source("Hello")
    _make_translation(src, "es", "Hola")

    tarball = tmp_path / "messages.tar.gz"
    export_to_tarball(tarball)
    assert tarball.exists()

    import_from_tarball(tarball)

    dest_po = locale_root / "es" / "LC_MESSAGES" / "django.po"
    assert dest_po.exists()
    po = polib.pofile(str(dest_po))
    msgids = {e.msgid for e in po}
    assert "Hello" in msgids


@pytest.mark.django_db
def test_import_reports_path_and_counts(tmp_path, settings, capsys):  # noqa: F811
    locale_root = tmp_path / "locale"
    locale_root.mkdir()
    settings.LOCALE_PATHS = [str(locale_root)]

    src = _make_source("Goodbye")
    _make_translation(src, "es", "Adiós")
    tarball = tmp_path / "messages.tar.gz"
    export_to_tarball(tarball)

    buf = _io.StringIO()
    import_from_tarball(tarball, stdout=buf)
    output = buf.getvalue()
    assert str(locale_root) in output
    assert "LOCALE_PATHS" in output


# ---------------------------------------------------------------------------
# Admin status computation
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_admin_status_not_translated():
    from dbi18n.admin import _status_for_language

    dbi18n_catalog.reset()
    src = _make_source("Untranslated xyz")
    assert _status_for_language(src, "es") == "not_translated"


@pytest.mark.django_db
def test_admin_status_translated_from_file():
    from dbi18n.admin import _status_for_language

    dbi18n_catalog.reset()
    sync_source_strings()
    src = SourceString.objects.get(msgid="Pending")
    # No DB row — falls through to file catalog.
    assert _status_for_language(src, "es") == "translated"


@pytest.mark.django_db
def test_admin_status_modified():
    from dbi18n.admin import _status_for_language

    dbi18n_catalog.reset()
    src = _make_source("Pending")
    _make_translation(src, "es", "Pendiente (modificado)")
    assert _status_for_language(src, "es") == "modified"
