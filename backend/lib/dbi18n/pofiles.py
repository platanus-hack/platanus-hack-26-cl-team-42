"""Helpers for reading and writing ``django.po`` catalog files.

All public functions work in terms of the standard ``django`` gettext domain.
:func:`locate_po_files` discovers every committed ``django.po`` under the
installed apps' ``locale/`` directories and the paths in ``settings.LOCALE_PATHS``.

:func:`catalog_fingerprint` computes a cheap mtime/size fingerprint used by
the admin to detect catalog staleness without re-parsing any ``.po``.

:func:`sync_source_strings` is the primary entry-point called by ``i18n_sync``
and the ``post_migrate`` hook.

:func:`prune` deletes Translation rows that are redundant vs the committed
file catalog plus stale SourceStrings.
"""

from __future__ import annotations

import io
import tarfile
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING

import polib
from django.apps import apps
from django.conf import settings
from django.utils import timezone

if TYPE_CHECKING:
    from io import TextIOBase  # noqa: F401


# ---------------------------------------------------------------------------
# Catalog file discovery
# ---------------------------------------------------------------------------


def locale_dirs() -> list[Path]:
    """Return all directories that may contain a ``<lang>/LC_MESSAGES/django.po``."""
    dirs: list[Path] = []
    for app_config in apps.get_app_configs():
        locale_dir = Path(app_config.path) / "locale"
        if locale_dir.is_dir():
            dirs.append(locale_dir)
    for path in getattr(settings, "LOCALE_PATHS", []):
        p = Path(path)
        if p.is_dir():
            dirs.append(p)
    return dirs


def locate_po_files() -> list[Path]:
    """Return all existing ``django.po`` paths, deduplicated."""
    seen: set[Path] = set()
    result: list[Path] = []
    for locale_dir in locale_dirs():
        for po_path in sorted(locale_dir.rglob("django.po")):
            resolved = po_path.resolve()
            if resolved not in seen:
                seen.add(resolved)
                result.append(po_path)
    return result


# ---------------------------------------------------------------------------
# Fingerprint
# ---------------------------------------------------------------------------


def catalog_fingerprint(po_files: list[Path] | None = None) -> str:
    """Cheap path+mtime+size fingerprint of all committed ``django.po`` files.

    If a file has disappeared since it was discovered, it is omitted silently.
    """
    if po_files is None:
        po_files = locate_po_files()
    lines: list[str] = []
    for p in sorted(po_files):
        try:
            st = p.stat()
            lines.append(f"{p}:{st.st_mtime:.6f}:{st.st_size}")
        except OSError:
            continue
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Plural-Forms helpers
# ---------------------------------------------------------------------------


#: Fallback plural rule (English-style) when a catalog declares none.
_DEFAULT_PLURAL_FORMS = "nplurals=2; plural=(n != 1);"


def plural_forms_header(language: str) -> str:
    """Return the full ``Plural-Forms`` header for *language* from its catalog.

    Reads the value Django's own catalog declares (e.g. Spanish ships
    ``nplurals=3``), so exported ``.po`` files match the runtime expectation.
    Falls back to the English-style rule.
    """
    from django.utils.translation import trans_real

    try:
        # Use the unpatched builder so DB rows don't interfere.
        from . import catalog as dbi18n_catalog

        builder = dbi18n_catalog._original_translation or trans_real.translation
        trans = builder(language)
        plural_forms = getattr(trans, "_info", {}).get("plural-forms", "")
        if "nplurals" in plural_forms:
            return plural_forms.strip()
    except Exception:
        pass
    return _DEFAULT_PLURAL_FORMS


def plural_form_count(language: str) -> int:
    """Return the number of plural forms for *language* from the committed catalog."""
    header = plural_forms_header(language)
    for part in header.split(";"):
        part = part.strip()
        if part.startswith("nplurals"):
            try:
                return int(part.split("=")[1].strip())
            except (IndexError, ValueError):
                break
    return 2


# ---------------------------------------------------------------------------
# Sync
# ---------------------------------------------------------------------------


def sync_source_strings(stdout: TextIOBase | None = None) -> int:
    """Parse all committed ``django.po`` files and upsert :class:`SourceString`.

    Returns the count of strings added or updated.

    - Strings that appear in the files are created/updated and marked not-stale.
    - Strings present in the DB but absent from every ``.po`` are marked stale.
    - Updates ``SyncState`` with the current fingerprint.
    """
    from .models import SourceString, SyncState

    po_files = locate_po_files()
    if not po_files:
        if stdout:
            stdout.write("No django.po files found; nothing to sync.\n")
        return 0

    # Collect all (context, msgid, msgid_plural) from every .po file.
    seen: dict[tuple[str, str], str] = {}  # (context, msgid) -> msgid_plural
    for po_path in po_files:
        try:
            po = polib.pofile(str(po_path))
        except Exception as exc:
            if stdout:
                stdout.write(f"  Warning: could not parse {po_path}: {exc}\n")
            continue
        for entry in po:
            key = (entry.msgctxt or "", entry.msgid)
            seen[key] = entry.msgid_plural or ""

    # Guard against the table not existing yet (e.g. when post_migrate fires
    # during the very migrate run that creates the dbi18n tables).
    from django.db import DatabaseError

    count = 0
    seen_pks: set[int] = set()
    try:
        for (context, msgid), msgid_plural in seen.items():
            obj, created = SourceString.objects.update_or_create(
                context=context,
                msgid=msgid,
                defaults={"msgid_plural": msgid_plural, "is_stale": False},
            )
            seen_pks.add(obj.pk)
            if created:
                count += 1

        # Mark vanished entries stale.
        stale_count = SourceString.objects.exclude(pk__in=seen_pks).update(is_stale=True)

        # Record fingerprint.
        fp = catalog_fingerprint(po_files)
        state = SyncState.get()
        state.fingerprint = fp
        state.synced_at = timezone.now()
        state.save(update_fields=["fingerprint", "synced_at"])
    except DatabaseError:
        return 0

    if stdout:
        stdout.write(
            f"Synced {count} new string(s) from {len(po_files)} catalog(s)."
            f" {stale_count} stale.\n"
        )
    return count


# ---------------------------------------------------------------------------
# Export
# ---------------------------------------------------------------------------


def export_to_tarball(output_path: Path, stdout: TextIOBase | None = None) -> None:
    """Write active Translation rows to a ``messages.tar.gz``.

    The tarball contains one ``locale/<lang>/LC_MESSAGES/django.po`` per
    language that has at least one non-blank Translation row.
    """
    from .models import Translation

    rows = list(
        Translation.objects.exclude(msgstr="")
        .select_related("source")
        .order_by("language", "source__msgid", "plural_index")
        .values_list(
            "language",
            "source__context",
            "source__msgid",
            "source__msgid_plural",
            "plural_index",
            "msgstr",
        )
    )

    # Group by language.
    by_lang: dict[str, list[tuple]] = {}
    for lang, context, msgid, msgid_plural, plural_index, msgstr in rows:
        by_lang.setdefault(lang, []).append((context, msgid, msgid_plural, plural_index, msgstr))

    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        for lang, entries in sorted(by_lang.items()):
            po = polib.POFile()
            po.metadata = {
                "Content-Type": "text/plain; charset=UTF-8",
                "Content-Transfer-Encoding": "8bit",
                "Language": lang,
            }
            po.metadata["Plural-Forms"] = plural_forms_header(lang)

            # Build entry objects; group plural forms under a single POEntry.
            entry_map: dict[tuple[str, str], polib.POEntry] = {}
            for context, msgid, msgid_plural, plural_index, msgstr in entries:
                key = (context or "", msgid)
                if key not in entry_map:
                    e = polib.POEntry(
                        msgctxt=context or None,
                        msgid=msgid,
                        msgid_plural=msgid_plural or None,
                        msgstr="" if msgid_plural else msgstr,
                        msgstr_plural={} if msgid_plural else None,
                    )
                    entry_map[key] = e
                if msgid_plural:
                    entry_map[key].msgstr_plural[plural_index] = msgstr

            for entry in entry_map.values():
                po.append(entry)

            po_bytes = str(po).encode("utf-8")
            po_path = f"locale/{lang}/LC_MESSAGES/django.po"
            info = tarfile.TarInfo(name=po_path)
            info.size = len(po_bytes)
            tar.addfile(info, io.BytesIO(po_bytes))
            if stdout:
                stdout.write(f"  {lang}: {len(entry_map)} string(s)\n")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(buf.getvalue())
    if stdout:
        stdout.write(f"Exported to {output_path}\n")


# ---------------------------------------------------------------------------
# Import
# ---------------------------------------------------------------------------


def import_from_tarball(
    tarball_path: Path,
    stdout: TextIOBase | None = None,
) -> None:
    """Read a ``messages.tar.gz`` and merge entries into ``LOCALE_PATHS[0]``.

    Entries clobber existing values.  Reports the target path, why it was
    chosen, and added/overwritten counts.
    """
    locale_paths = getattr(settings, "LOCALE_PATHS", [])
    if not locale_paths:
        raise ValueError(
            "LOCALE_PATHS is empty. Add a project-level locale directory "
            "(e.g. BASE_DIR / 'locale') as the first entry."
        )
    target_root = Path(locale_paths[0])
    if stdout:
        stdout.write(
            f"Target: {target_root}\n"
            f"  (first LOCALE_PATHS entry — Django gives this the highest "
            f"file-catalog priority, overriding app-level catalogs)\n"
        )

    with tarfile.open(tarball_path, "r:gz") as tar:
        for member in tar.getmembers():
            if not member.name.endswith("django.po"):
                continue
            # Expected: locale/<lang>/LC_MESSAGES/django.po
            parts = Path(member.name).parts
            if len(parts) < 4:
                continue
            lang = parts[1]
            f = tar.extractfile(member)
            if f is None:
                continue
            po_bytes = f.read()

            dest = target_root / lang / "LC_MESSAGES" / "django.po"
            dest.parent.mkdir(parents=True, exist_ok=True)

            added = overwritten = 0
            if dest.exists():
                existing = polib.pofile(str(dest))
                existing_map: dict[tuple[str | None, str], polib.POEntry] = {
                    (e.msgctxt, e.msgid): e for e in existing
                }
            else:
                existing = polib.POFile()
                existing.metadata = {
                    "Content-Type": "text/plain; charset=UTF-8",
                    "Content-Transfer-Encoding": "8bit",
                    "Language": lang,
                }
                existing_map = {}

            with tempfile.NamedTemporaryFile(suffix=".po", delete=False) as tmp:
                tmp.write(po_bytes)
                tmp_path = tmp.name
            try:
                incoming = polib.pofile(tmp_path, encoding="utf-8")
            finally:
                Path(tmp_path).unlink(missing_ok=True)
            for entry in incoming:
                key = (entry.msgctxt, entry.msgid)
                if key in existing_map:
                    existing_map[key].msgstr = entry.msgstr
                    if entry.msgstr_plural:
                        existing_map[key].msgstr_plural = entry.msgstr_plural
                    overwritten += 1
                else:
                    existing.append(entry)
                    added += 1

            existing.save(str(dest))
            if stdout:
                stdout.write(
                    f"  {lang}: +{added} added, {overwritten} overwritten → {dest}\n"
                )


# ---------------------------------------------------------------------------
# Prune
# ---------------------------------------------------------------------------


def prune(stdout: TextIOBase | None = None) -> tuple[int, int]:
    """Delete redundant Translation rows and stale SourceStrings.

    A Translation is redundant when its ``msgstr`` equals the value that the
    committed ``.mo`` catalog already provides (``catalog.file_value``).

    Returns ``(translation_count, source_string_count)`` of deleted objects.
    """
    from django.db import DatabaseError

    from . import catalog as dbi18n_catalog
    from .models import SourceString, Translation

    t_deleted = 0
    try:
        rows = list(
            Translation.objects.exclude(msgstr="")
            .select_related("source")
            .values_list("pk", "language", "source__context", "source__msgid", "msgstr")
        )
    except DatabaseError:
        if stdout:
            stdout.write("dbi18n tables not migrated yet; nothing to prune.\n")
        return 0, 0
    redundant_pks = []
    for pk, language, context, msgid, msgstr in rows:
        file_val = dbi18n_catalog.file_value(language, context, msgid)
        if file_val is not None and file_val == msgstr:
            redundant_pks.append(pk)

    if redundant_pks:
        t_deleted, _ = Translation.objects.filter(pk__in=redundant_pks).delete()

    stale_qs = SourceString.objects.filter(is_stale=True)
    ss_deleted, _ = stale_qs.delete()

    dbi18n_catalog.reset()

    if stdout:
        stdout.write(
            f"Pruned {t_deleted} redundant translation(s), "
            f"{ss_deleted} stale source string(s).\n"
        )
    return t_deleted, ss_deleted
