# Backend deepdive

The backend is a Django app in `backend/`. It exposes Django views, Django Allauth auth routes, and a Django Ninja API.

## Entry points

```txt
backend/manage.py
backend/asgi.py
backend/wsgi.py
backend/conf/settings.py
backend/conf/urls.py
```

`conf/settings.py` contains the main Django settings. `conf/urls.py` wires the URL routes up and creates the Ninja API instance.

## App layout

```txt
backend/apps/users/      custom user model and user views
backend/apps/demo/       demo app, incl. example Celery tasks (tasks.py)
backend/lib/             vendored libraries (e.g. celery-tracker)
backend/tests/           backend tests (unit + e2e)
```

Installed local apps:

```py
"apps.users"
"apps.demo"
```

## Configuration

Settings are loaded from environment variables using `uncouple` config classes.

Main config classes in `conf/settings.py`:

- `DjangoConfig`
- `EmailConfig`
- `CeleryConfig`
- `ProjectConfig`


Common local values are defined in:

```txt
local/conf/local.example
```

The default local database URL points to the Postgres service we can spin up with Docker Compose:

```txt
postgresql://postgres:postgres@postgres:5432/webapp
```

## URLs

All backend URLs are mounted under `settings.URL_PREFIX`, which defaults to `-`.

Main local URL groups:

| Path | Description |
| --- | --- |
| `/-/admin/` | Django admin |
| `/-/users/` | user views |
| `/-/.auth/accounts/` | Django Allauth account URLs |
| `/-/.auth/headless/` | Django Allauth headless API |
| `/-/api/` | Django Ninja API |
| `/-/api/docs` | Django Ninja API docs |
| `/-/_health/` | health check |

The admin route uses `settings.ADMIN_PATH`, which defaults to `admin/`. `LOGIN_URL` and `STATIC_URL` are also prefixed with `settings.URL_PREFIX`.

## API setup

The Ninja API is created in:

```txt
backend/conf/urls.py
```

It uses session auth:

```py
SessionAuth(csrf=False)
```

Routers are registered through `API_ROUTERS`. The current custom routers are:

```txt
/-/api/tracker
/-/api/eventcore   (live documentation graph; UI at /-/eventcore-docs/)
```

## Users app

The users app defines the custom user model:

```txt
backend/apps/users/models.py
```

`apps.users.User` extends Django `AbstractUser`.

Key behavior:

- email is unique
- email is used as `USERNAME_FIELD`
- username is disabled
- first name and last name are disabled
- `name` is available as a display field

Related files:

```txt
backend/apps/users/managers.py
backend/apps/users/forms.py
backend/apps/users/admin.py
backend/apps/users/urls.py
backend/apps/users/views.py
```

## Auth

Authentication is handled by Django Allauth.

Enabled pieces include:

- `allauth.account`
- `allauth.socialaccount`
- `allauth.socialaccount.providers.amazon_cognito`
- `allauth.headless`
- `allauth.usersessions`

The frontend mainly uses the headless routes under:

```txt
/-/.auth/headless/
```

Current account settings:

- registration is enabled
- login is by email
- email verification is disabled
- social account email authentication is enabled

The local development entrypoint does not create a superuser. Set `DJANGO_SUPERUSER_EMAIL` and `DJANGO_SUPERUSER_PASSWORD` in `local/conf/local` to seed one on first start, or run `just local createsuperuser`.

## Background tasks

Celery handles asynchronous work, with Redis as the broker and result backend
(the `CELERY_*` settings in `conf/settings.py`, fed by `CeleryConfig`).

```txt
backend/conf/celery.py        Celery app (started with `celery -A conf worker`)
backend/apps/demo/tasks.py    example task (demo.tasks.sample_task)
backend/lib/tracker/          vendored celery-tracker (import name `tracker`)
```

`conf/__init__.py` re-exports the Celery app as `conf.celery_app`, and tasks are
auto-discovered from the `tasks` module of every installed app.

The `tracker` library records task steps and progress and serves them through
the `/-/api/tracker` router (created in `conf/urls.py`), which the frontend
`/tracker` page consumes. In the local stack a dedicated `worker` service runs
the Celery worker, restarting on code changes.

`backend/lib/` is on the Python path, so vendored packages like `tracker` are
importable by their top-level name; see `backend/lib/README.md` for how it is
pinned and updated.

## Static and media files

Static files are served by Whitenoise.

This is mostly for Django-owned assets, such as admin CSS/JS and any static files used by backend-rendered pages. User-facing React assets should usually live in the frontend instead.

Configured storage backend:

```py
whitenoise.storage.CompressedManifestStaticFilesStorage
```

`backend/staticfiles/` is generated output from Django `collectstatic`. It is not a source directory for app assets.

Media files are different from static files. They are for uploaded or generated user content. The local media root is:

```txt
backend/apps/media/
```

## Internationalization (i18n)

Strings are marked for translation the standard Django way (`gettext` /
`gettext_lazy`) and stored in committed `django.po` files (standard domain).
A live database overlay (`dbi18n`, `lib/dbi18n`) lets translators edit strings
in the admin without a redeploy. See its README (surfaced at
[dev/lib/dbi18n](./lib/dbi18n.md)) for the full design and workflow.

Settings (`conf/settings.py`):

- `USE_I18N = True`
- `LANGUAGE_CODE` — default language, configurable via `DJANGO_LANGUAGE_CODE`
- `LANGUAGES` — the languages the project offers (ships with `en` and `es`)
- `LOCALE_PATHS = [BASE_DIR / "locale"]` — project-level consolidated catalog;
  highest file-catalog priority; target for `i18n_import`
- `django.middleware.locale.LocaleMiddleware` resolves the active language per
  request (from the `Accept-Language` header, session, or cookie)
- `dbi18n.middleware.DbTranslationMiddleware` (right after `LocaleMiddleware`)
  keeps each worker's catalog fresh
- `DBI18N_RELOAD_SECONDS` — how quickly DB edits propagate across workers

Mark strings for translation with `gettext`/`gettext_lazy` as usual:

```py
from django.utils.translation import gettext_lazy as _

name = CharField(_("Name of User"), max_length=255)
```

For runtime interpolation, prefer **named** placeholders so translators can
reorder them:

```py
_("Order %(order_id)s not found") % {"order_id": order_id}
```

Worked examples live in `apps/users/` and `apps/demo/` (model field labels,
`TextChoices` labels, and the demo's `CommandError` messages).

### Managing translations

Open the admin → **Database translations → Source strings**.  Every string
extracted from the committed `django.po` files appears here with a per-language
status column:

- **—** Not translated
- **✓** Translated (covered by the committed `.po`)
- **✎** Modified — the DB override is **live immediately**; export and commit it
  to make it permanent

The full loop:

1. **Extract** — `just backend messages <lang>` (wraps `makemessages`)
2. **Compile** — `just backend compilemessages` (or done automatically at image
   build / dev container startup)
3. **Sync** — automatic on `migrate`; also available via the admin **Sync** button
4. **Edit** — admin → Source strings → click a string → edit Translation rows
5. **Export** — admin **Download messages.tar.gz** or `manage.py i18n_export`
6. **Import** — `just backend i18n-import messages.tar.gz` on a dev machine
7. **Commit** — commit the updated `.po` files; deploy
8. **Prune** — admin **Prune redundant translations** action after deploy

The demo app ships its Spanish strings as a committed
`apps/demo/locale/es/LC_MESSAGES/django.po` so the feature works out of the
box without any seeding step.

To add a language, list it in `LANGUAGES` and run `just backend messages <lang>`.

## Local development

Each layer's justfile is mounted as a submodule of the root justfile, so
commands run from the generated project root as `just <layer> <recipe>`.

Bring up the local Docker Compose environment:

```sh
just local up
```

`just local up` prints the local app URL and the seeded local dev credentials.

Run backend tests and management commands against the container:

```sh
just local test-unit
just local test-e2e
just local manage check
```

The backend also has its own justfile for host-side commands via `uv`:

```sh
just backend check
just backend makemigrations
just backend runserver
```

## Dependencies

Python dependencies are managed with `uv` in `backend/`.

Main dependency files:

```txt
backend/pyproject.toml
backend/uv.lock
```

Dev tools include:

- pytest, pytest-django, pytest-xdist
- httpx (e2e tests)
- ruff
- django-extensions
- watchdog (worker autoreload)

## Docker image

The backend Dockerfile is:

```txt
backend/docker/Dockerfile
```

It has three main targets:

- `development`: installs production and dev dependencies
- `build`: builds production wheels
- `runtime`: production image running as a non-root user
