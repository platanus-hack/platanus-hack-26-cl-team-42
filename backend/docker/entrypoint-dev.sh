#!/bin/bash
set -e

# Always seed a known dev login so the local stack is usable out of the box.
# Override via DJANGO_SUPERUSER_EMAIL / DJANGO_SUPERUSER_PASSWORD.
export DJANGO_SUPERUSER_EMAIL="${DJANGO_SUPERUSER_EMAIL:-test@localhost}"
export DJANGO_SUPERUSER_PASSWORD="${DJANGO_SUPERUSER_PASSWORD:-test}"

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
email = os.environ['DJANGO_SUPERUSER_EMAIL']
if not User.objects.filter(email=email).exists():
    User.objects.create_superuser(email=email, password=os.environ['DJANGO_SUPERUSER_PASSWORD'])
"
# No collectstatic here: with DEBUG, runserver serves static straight from the
# staticfiles finders, and dev-user cannot write into the bind-mounted /app
# (which fails collectstatic on Linux/CI and kills the container).
exec python manage.py runserver_plus 0.0.0.0:8000
