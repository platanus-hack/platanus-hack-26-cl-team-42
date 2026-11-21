manage *args:
    DJANGO_SECRET_KEY=dummy DJANGO_URL_PREFIX=- uv run manage.py {{args}}

# Extract translatable strings into locale/<lang>/LC_MESSAGES/django.po
# Requires gettext to be installed on the host (brew install gettext / apt install gettext).
messages lang:
    DJANGO_SECRET_KEY=dummy DJANGO_URL_PREFIX=- uv run manage.py makemessages \
        -l {{lang}} --ignore=.venv --ignore=lib

# Compile all django.po files → django.mo
compilemessages:
    DJANGO_SECRET_KEY=dummy DJANGO_URL_PREFIX=- uv run manage.py compilemessages \
        --ignore=.venv --ignore=lib

# Import a messages.tar.gz from a live environment into LOCALE_PATHS[0]
# Run 'just backend compilemessages' afterwards to compile the updated .po files.
i18n-import tarball:
    DJANGO_SECRET_KEY=dummy DJANGO_URL_PREFIX=- uv run manage.py i18n_import {{tarball}}

check:
    DJANGO_SECRET_KEY=dummy DJANGO_URL_PREFIX=- uv run manage.py check

makemigrations *args:
    DJANGO_SECRET_KEY=dummy DJANGO_URL_PREFIX=- uv run manage.py makemigrations {{args}}

migrate *args:
    DJANGO_SECRET_KEY=dummy DJANGO_URL_PREFIX=- uv run manage.py migrate {{args}}

test *args:
    DJANGO_SECRET_KEY=dummy DJANGO_URL_PREFIX=- uv run manage.py test {{args}}

shell:
    DJANGO_SECRET_KEY=dummy DJANGO_URL_PREFIX=- uv run manage.py shell

createsuperuser:
    DJANGO_SECRET_KEY=dummy DJANGO_URL_PREFIX=- uv run manage.py createsuperuser

runserver *args:
    DJANGO_SECRET_KEY=dummy DJANGO_URL_PREFIX=- uv run manage.py runserver_plus 0.0.0.0:8000 {{args}}
