# dbi18n

Translation **management** for Django on top of the standard
[gettext](https://docs.djangoproject.com/en/stable/topics/i18n/translation/)
pipeline: committed `django.po` files are the source of truth, and a live
database overlay lets translators edit strings from the admin — with changes
visible immediately, no redeploy.

It deliberately does *not* replace gettext. Strings are marked the normal way,
`makemessages`/`compilemessages` work as usual, and the committed catalogs are
what ships. The database is an editing buffer: overrides are live at runtime,
then exported back into the `.po` files and pruned.

`lib/` is on the Python path, so it installs as a top-level app:

```python
INSTALLED_APPS = [..., "dbi18n", ...]

MIDDLEWARE = [
    ...,
    "django.middleware.locale.LocaleMiddleware",
    "dbi18n.middleware.DbTranslationMiddleware",  # after LocaleMiddleware
    ...,
]

LOCALE_PATHS = [BASE_DIR / "locale"]  # first entry = import target
```

## Quickstart

Mark strings as usual — nothing dbi18n-specific:

```python
from django.utils.translation import gettext_lazy as _, ngettext

status = _("Pending")
message = _("Order %(order_id)s not found") % {"order_id": order_id}
count_label = ngettext("%(n)s item", "%(n)s items", n) % {"n": n}
```

Extract and commit catalogs the standard way — `just backend messages <lang>`
wraps `makemessages` and writes `<app>/locale/<lang>/LC_MESSAGES/django.po`.

From there the dbi18n loop takes over:

1. **Sync** (automatic on every `migrate`, or the admin's Sync button) parses
   the committed `.po` files and mirrors every string into the database.
2. A translator opens **admin → Database translations → Source strings** and
   edits a translation. The change is **live immediately** — within
   `DBI18N_RELOAD_SECONDS` (default 30) on every worker — no redeploy.
3. When edits have accumulated, a developer clicks **Download
   messages.tar.gz** in the admin, then on a dev machine runs
   `just backend i18n-import messages.tar.gz`, commits the updated `.po`
   files, and deploys.
4. After deploying, the admin's **Prune redundant translations** action
   deletes DB rows that now match the committed catalogs.

At runtime a message resolves through, in order:

```
Translation rows (live DB overlay)
  → committed django.mo (LOCALE_PATHS > app locale/ dirs)
    → bundled package catalogs (Django admin, allauth, …)
      → the source string itself
```

The full cycle at a glance:

```
mark _( ) → makemessages → commit .po → compile .mo (image build / dev entrypoint)
     ↓
  sync (post_migrate / admin button) → edit in admin → LIVE immediately
     ↓
  export (admin download) → i18n-import (dev machine) → commit .po → deploy → prune
```

## Reference

### Concepts

| Concept | What it is |
| --- | --- |
| `SourceString` | One translatable string from the committed `.po` universe (context, msgid, optional plural form). |
| `Translation` | One translated form for a `(source, language, plural_index)`. The live overlay; wins over files at runtime. |
| `SyncState` | Singleton fingerprint of the catalog files at last sync; powers the admin's staleness indicator. |
| Sync | Parse committed `django.po` files → upsert `SourceString`s, mark vanished ones stale. Automatic on `post_migrate`; also an admin button. |
| Export | Pack the DB overlay into `messages.tar.gz` (one `.po` per language). Admin download or `manage.py i18n_export`. |
| Import | Merge an exported tarball into the first `LOCALE_PATHS` entry (clobbers). `manage.py i18n_import` / `just backend i18n-import`. |
| Prune | Delete DB rows equal to the committed catalog value, and stale `SourceString`s. Admin action. |

### The workflow, step by step

1. **Mark** strings with `gettext` / `gettext_lazy` / `ngettext` / `pgettext`.
2. **Extract** — `just backend messages <lang>` (wraps `makemessages`; needs
   `gettext` on the host) writes `<app>/locale/<lang>/LC_MESSAGES/django.po`.
3. **Sync** — automatic on every `migrate`; the admin's Sync button covers the
   in-between (it is highlighted when catalog files changed since last sync).
4. **Edit** — admin → **Database translations → Source strings**. Edits are
   live immediately in the editing worker and within `DBI18N_RELOAD_SECONDS`
   everywhere else.
5. **Export** — admin **Download messages.tar.gz** (or `manage.py i18n_export`).
6. **Import** — on a dev machine, `just backend i18n-import messages.tar.gz`
   merges the tarball into `LOCALE_PATHS[0]` (`backend/locale/`), clobbering
   existing entries, and reports what it wrote where. Then
   `just backend compilemessages` and commit the `.po` changes.
7. **Deploy** — the image build compiles the catalogs; `migrate` re-syncs.
8. **Prune** — admin action **Prune redundant translations** deletes DB rows
   whose value now matches the committed catalog, plus stale source strings.

### The admin

**Changelist** (Source strings): one row per string, with a column per
language in `settings.LANGUAGES` showing the *effective* message:

| Column shows | Meaning |
| --- | --- |
| `—` | Not translated: nothing in the `.po` nor the DB. |
| `{message}` | The committed `.po` value serves (no differing DB row). |
| `✎ {message}` | A live DB override differs from the committed value — pending export. |

The toolbar has **Sync** (disabled when catalogs are in sync, highlighted with
a changed-file count otherwise) and **Download messages.tar.gz**. Adding
source strings by hand is disabled — the universe comes from the `.po` files.

**Change page**: the source fields are read-only; a **Committed .po
translations** table shows what the compiled catalogs hold per language (and
per plural form), next to the editable `Translation` inline rows. For
pluralized strings the inline shows one row per plural form, labeled
*Singular* / *Plural form N* — indices follow the language's `Plural-Forms`
expression (e.g. Django ships Spanish with `nplurals=3`).

### Management commands

| Command | Does |
| --- | --- |
| `i18n_sync` | Parse committed `django.po` files, upsert `SourceString`s, mark vanished ones stale, record the sync fingerprint. |
| `i18n_export [-o path]` | Write the DB overlay as `messages.tar.gz` (`locale/<lang>/LC_MESSAGES/django.po` per language). |
| `i18n_import <tarball>` | Merge a tarball into `LOCALE_PATHS[0]`, clobbering; reports target path and added/overwritten counts. Compile afterwards. |
| `i18n_prune` | Delete DB rows equal to the committed catalog value, and stale `SourceString`s. Same as the admin **Prune redundant** button; run on a live env after committing translations. |

Host-side justfile recipes: `just backend messages <lang>`,
`just backend compilemessages`, `just backend i18n-import <tarball>`.

### Settings

| Setting | Default | Meaning |
| --- | --- | --- |
| `LOCALE_PATHS` | `[BASE_DIR / "locale"]` | First entry is the consolidated project catalog and the `i18n_import` target. Django gives it top file-catalog priority. |
| `DBI18N_RELOAD_SECONDS` | `30` | Max seconds before a worker rebuilds its catalog to pick up edits from other processes. |

### Per-app vs project-level catalogs

Each app can keep its own `locale/` directory
(`<app>/locale/<lang>/LC_MESSAGES/django.po`) — the demo app does. The
project-level `LOCALE_PATHS[0]` (`backend/locale/`) has higher Django
priority and is where imports land. Sync and export read from all of them.

### How it works

- **Catalog patch** — `dbi18n.catalog.install()` (from `AppConfig.ready`)
  wraps Django's `trans_real.translation()`. After Django builds a language's
  catalog from its usual sources, active `Translation` rows are layered on
  top. Plural rows write gettext tuple keys `(msgid, index)`; form 0 also
  fills the plain key, mirroring `.mo` semantics. The patch is idempotent.
- **Freshness** — catalogs are cached per process. Edits propagate instantly
  in the editing process (`post_save`/`post_delete` signal resets the catalog)
  and within `DBI18N_RELOAD_SECONDS` in every other worker via a cheap
  per-request time-gated reset — no shared cache required.
- **Universe & staleness** — `i18n_sync` runs on `post_migrate` so deployed
  environments always reflect the shipped catalogs. `SyncState` stores a
  path+mtime+size fingerprint; the admin re-stats the files per changelist
  load to decide whether the Sync button matters (no `.po` parsing).
- **Compilation** — `.mo` files are gitignored. The production image compiles
  every `django.po` with `msgfmt` during the Docker build; the dev container
  entrypoint runs `compilemessages` (with a `sudo` fallback for read-only
  Linux bind mounts).

### Scope / limitations

- Resolution wraps a documented-but-internal Django hook
  (`trans_real.translation`); exercised by this template's tests.
- The `django` domain only — JavaScript strings would need a separate
  `djangojs` catalog (not covered by dbi18n).
- Translators can only translate synced strings; free-form msgids can't be
  added from the admin (by design — the `.po` universe is the contract).
