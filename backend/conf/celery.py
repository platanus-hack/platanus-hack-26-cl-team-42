"""Celery application for this Django project.

Import path used by workers:
    celery -A conf.celery worker --loglevel=info

The ``conf/__init__.py`` re-exports ``celery_app`` so that Django's
``AppConfig.ready()`` and other startup hooks see it automatically.
"""

import os

from celery import Celery

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "conf.settings")

app = Celery("webapp")

# Read configuration from Django settings using the CELERY_ namespace.
app.config_from_object("django.conf:settings", namespace="CELERY")

# Auto-discover ``tasks`` modules in every INSTALLED_APP (e.g. ``apps.demo``).
app.autodiscover_tasks()
