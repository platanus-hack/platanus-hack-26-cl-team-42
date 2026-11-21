"""Django admin for dbi18n.

SourceStringAdmin is the single editing surface.  Each source string exposes
its Translation rows through an inline whose language field is a dropdown
limited to settings.LANGUAGES; ``plural_index`` stays 0 for plain strings and
selects the gettext plural form for pluralized ones.

The changelist adds two toolbar buttons (Sync, Download) and an action
(Prune redundant translations).  A sync-state indicator gates the Sync button:
greyed/disabled when fingerprint matches, highlighted with a change count when
catalog files have been modified since the last sync.
"""

from __future__ import annotations

from django import forms
from django.conf import settings
from django.contrib import admin, messages
from django.db import models
from django.forms import Textarea
from django.http import HttpResponse
from django.shortcuts import redirect
from django.urls import path, reverse
from django.utils import timezone
from django.utils.html import format_html
from django.utils.text import Truncator
from django.utils.translation import gettext_lazy as _

from . import catalog as dbi18n_catalog
from .models import SourceString, SyncState, Translation
from .pofiles import (
    catalog_fingerprint,
    export_to_tarball,
    locate_po_files,
    prune,
    sync_source_strings,
)

# ---------------------------------------------------------------------------
# Status helpers (must be defined before SourceStringAdmin is instantiated
# at module import time via @admin.register).
# ---------------------------------------------------------------------------


def _status_for_language(source: SourceString, lang: str) -> str:
    """Compute the status keyword for one (source, language) pair.

    - "not_translated": no committed value and no DB row
    - "translated": committed value present, no differing DB override
    - "modified": DB row differs from the committed value (live, pending export)
    """
    db_rows = {t.plural_index: t.msgstr for t in source.translations.filter(language=lang)}
    file_val = dbi18n_catalog.file_value(lang, source.context, source.msgid)

    if not db_rows:
        return "translated" if file_val else "not_translated"

    for msgstr in db_rows.values():
        if msgstr and msgstr != file_val:
            return "modified"
    return "translated"


def _make_status_method(lang: str, lang_name: str):
    """Return a changelist column method that renders the message for a language.

    Column content:
    - ``—``               nothing in the .po nor the DB
    - ``{po value}``      committed value serves (DB empty or equal to it)
    - ``✎ {db value}``   DB override differs from the committed value (live)

    For pluralized strings the singular (form 0) is shown.
    """

    def status_method(self, obj: SourceString):
        file_val = dbi18n_catalog.file_value(lang, obj.context, obj.msgid)
        db_rows = {t.plural_index: t.msgstr for t in obj.translations.filter(language=lang)}
        db_val = db_rows.get(0, "")

        if db_val and db_val != file_val:
            return format_html(
                '<span style="color:#e65c00;font-weight:bold;" title="{}">✎</span> {}',
                _("Modified — live DB override, pending export"),
                Truncator(db_val).chars(60),
            )
        if file_val:
            return format_html("{}", Truncator(file_val).chars(60))
        return format_html('<span style="color:#999;">—</span>')

    status_method.short_description = lang_name
    status_method.allow_tags = True
    status_method.__name__ = f"_status_{lang}"
    return status_method


def _count_changed_files(old_fp: str, new_fp: str) -> int:
    """Count files whose fingerprint lines differ between two fingerprint strings."""
    old_lines = set(old_fp.splitlines())
    new_lines = set(new_fp.splitlines())
    return len(new_lines.symmetric_difference(old_lines))


# ---------------------------------------------------------------------------
# Inline
# ---------------------------------------------------------------------------


def _plural_index_choices(source: SourceString) -> list[tuple[int, str]]:
    """Labeled plural-form choices for a pluralized source's ``plural_index``.

    "Singular" plus one "Plural form N" per gettext form the languages declare.
    Only used when ``source.is_plural`` (plain strings hide the field entirely).
    """
    from .pofiles import plural_form_count

    max_forms = max(
        (plural_form_count(lang) for lang, _name in settings.LANGUAGES),
        default=2,
    )
    choices = [(0, _("Singular"))]
    choices += [(i, _("Plural form %(n)s") % {"n": i}) for i in range(1, max_forms)]
    return choices


class TranslationForm(forms.ModelForm):
    """Inline form: language limited to settings.LANGUAGES."""

    language = forms.ChoiceField(label=_("Language"), choices=settings.LANGUAGES)

    class Meta:
        model = Translation
        fields = ("language", "plural_index", "msgstr")


class TranslationInline(admin.TabularInline):
    model = Translation
    form = TranslationForm
    extra = 1
    formfield_overrides = {
        models.TextField: {"widget": Textarea(attrs={"rows": 2, "cols": 60})},
    }

    def get_queryset(self, request):
        return super().get_queryset(request).select_related("source")

    def get_fields(self, request, obj=None):
        # Plain strings only ever use form 0, so the plural selector is noise —
        # omit it (the model default of 0 applies). Show it only for plurals.
        if obj is not None and obj.is_plural:
            return ("language", "plural_index", "msgstr")
        return ("language", "msgstr")

    def get_formset(self, request, obj=None, **kwargs):
        formset = super().get_formset(request, obj, **kwargs)
        if obj is not None and obj.is_plural:
            formset.form.base_fields["plural_index"] = forms.TypedChoiceField(
                label=_("Form"),
                choices=_plural_index_choices(obj),
                coerce=int,
                empty_value=0,
            )
        return formset


# ---------------------------------------------------------------------------
# Admin
# ---------------------------------------------------------------------------


@admin.register(SourceString)
class SourceStringAdmin(admin.ModelAdmin):
    change_list_template = "admin/dbi18n/sourcestring/change_list.html"

    list_display = ["msgid_display", "context", "stale_display"] + [
        f"_status_{lang}" for lang, _ in settings.LANGUAGES
    ]
    list_filter = ["is_stale"]
    search_fields = ["msgid", "context"]
    ordering = ["msgid", "context"]
    inlines = [TranslationInline]

    # Source strings mirror the committed .po files; only the DB Translation
    # overlay (the inline) is editable. Everything else is shown read-only.
    readonly_fields = (
        "msgid",
        "context",
        "msgid_plural",
        "is_stale",
        "updated_at",
        "file_translations",
    )

    def has_add_permission(self, request):
        return False

    def get_queryset(self, request):
        return super().get_queryset(request).prefetch_related("translations")

    @admin.display(description=_("source string"), ordering="msgid")
    def msgid_display(self, obj):
        return format_html(
            '<div style="white-space:normal; max-width:32em;">{}</div>', obj.msgid
        )

    @admin.display(description=_("Stale (removed from .po)"), boolean=True)
    def stale_display(self, obj):
        return obj.is_stale

    @admin.display(description=_("Committed .po translations"))
    def file_translations(self, obj):
        """Read-only table of the values already in the committed .po/.mo files."""
        if obj is None or obj.pk is None:
            return "—"

        forms = [(0, _("Singular") if obj.is_plural else None)]
        if obj.is_plural:
            # Discover how many plural forms each language declares; take the max
            # so the table has a row per form.
            from .pofiles import plural_form_count

            max_forms = max(
                (plural_form_count(lang) for lang, _name in settings.LANGUAGES),
                default=2,
            )
            for i in range(1, max_forms):
                forms.append((i, _("Plural form %(n)s") % {"n": i}))

        rows = []
        for lang, lang_name in settings.LANGUAGES:
            for plural_index, form_label in forms:
                value = dbi18n_catalog.file_value(
                    lang, obj.context, obj.msgid, plural_index if obj.is_plural else None
                )
                label = lang_name if form_label is None else f"{lang_name} · {form_label}"
                rows.append(
                    format_html(
                        "<tr><th style='text-align:left;padding-right:1em;'>{}</th>"
                        "<td>{}</td></tr>",
                        label,
                        value or format_html('<span style="color:#999;">—</span>'),
                    )
                )
        return format_html(
            "<table style='border-collapse:collapse;'>{}</table>",
            format_html("".join(rows)),
        )

    def __init__(self, model, admin_site):
        super().__init__(model, admin_site)
        # Attach one status method per language at first instantiation.
        for lang, lang_name in settings.LANGUAGES:
            method_name = f"_status_{lang}"
            if not hasattr(self.__class__, method_name):
                setattr(
                    self.__class__,
                    method_name,
                    _make_status_method(lang, lang_name),
                )

    # --- changelist extra context -------------------------------------------

    def changelist_view(self, request, extra_context=None):
        extra = extra_context or {}
        extra.update(self._sync_indicator_context())
        extra["dbi18n_sync_url"] = reverse("admin:dbi18n_sync")
        extra["dbi18n_export_url"] = reverse("admin:dbi18n_export")
        extra["dbi18n_prune_url"] = reverse("admin:dbi18n_prune")
        return super().changelist_view(request, extra_context=extra)

    def _sync_indicator_context(self) -> dict:
        state = SyncState.get()
        po_files = locate_po_files()
        current_fp = catalog_fingerprint(po_files)
        sync_needed = current_fp != state.fingerprint

        if sync_needed:
            changed = _count_changed_files(state.fingerprint, current_fp)
            info = None
        else:
            changed = 0
            synced_at = state.synced_at
            if synced_at:
                info = _("Catalogs in sync (last synced %(dt)s)") % {
                    "dt": timezone.localtime(synced_at).strftime("%Y-%m-%d %H:%M")
                }
            else:
                info = _("Catalogs in sync")

        return {
            "dbi18n_sync_needed": sync_needed,
            "dbi18n_changed_files": changed,
            "dbi18n_sync_info": None if sync_needed else info,
        }

    # --- custom URLs --------------------------------------------------------

    def get_urls(self):
        custom = [
            path(
                "sync/",
                self.admin_site.admin_view(self._sync_view),
                name="dbi18n_sync",
            ),
            path(
                "export/",
                self.admin_site.admin_view(self._export_view),
                name="dbi18n_export",
            ),
            path(
                "prune/",
                self.admin_site.admin_view(self._prune_view),
                name="dbi18n_prune",
            ),
        ]
        return custom + super().get_urls()

    def _sync_view(self, request):
        count = sync_source_strings(stdout=None)
        messages.success(request, _("Sync complete: %(n)s new string(s) added.") % {"n": count})
        return redirect(reverse("admin:dbi18n_sourcestring_changelist"))

    def _export_view(self, request):
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as tmpdir:
            out = Path(tmpdir) / "messages.tar.gz"
            export_to_tarball(out, stdout=None)
            data = out.read_bytes()

        response = HttpResponse(data, content_type="application/gzip")
        response["Content-Disposition"] = 'attachment; filename="messages.tar.gz"'
        return response

    def _prune_view(self, request):
        # Mutating, so only act on POST; GET just returns to the changelist.
        changelist_url = reverse("admin:dbi18n_sourcestring_changelist")
        if request.method == "POST":
            t_count, ss_count = prune(stdout=None)
            messages.success(
                request,
                _("Pruned %(t)s redundant translation(s) and %(ss)s stale source string(s).")
                % {"t": t_count, "ss": ss_count},
            )
        return redirect(changelist_url)
