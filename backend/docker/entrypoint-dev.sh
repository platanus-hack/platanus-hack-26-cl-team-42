#!/bin/bash
set -e

# No superuser is created by default. To seed one for development, set both
# DJANGO_SUPERUSER_EMAIL and DJANGO_SUPERUSER_PASSWORD in the local profile (or create one with
# `just local createsuperuser`). There is no default password.

python manage.py migrate --noinput

# Compile django.po → django.mo for the dev container.  On macOS/OrbStack the
# bind mount is writable by dev-user, so the plain invocation succeeds.  On
# Linux the bind mount may be owned by the host user; the sudo fallback works
# because dev-user has passwordless sudo in the dev image.
python manage.py compilemessages --ignore=.venv --ignore=lib 2>/dev/null \
    || sudo python manage.py compilemessages --ignore=.venv --ignore=lib \
    || echo "Warning: compilemessages failed — translations may fall back to source strings"
python manage.py shell -c "
import os

from django.contrib.auth import get_user_model

User = get_user_model()
email = os.environ.get('DJANGO_SUPERUSER_EMAIL')
password = os.environ.get('DJANGO_SUPERUSER_PASSWORD')
if email and password and not User.objects.filter(email=email).exists():
    User.objects.create_superuser(email=email, password=password)
"
# No collectstatic here: with DEBUG, runserver serves static straight from the
# staticfiles finders, and dev-user cannot write into the bind-mounted /app
# (which fails collectstatic on Linux/CI and kills the container).
exec python manage.py runserver_plus 0.0.0.0:8000
