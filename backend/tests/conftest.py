"""Backend unit test fixtures.

Unit tests run in-process (no running server required, unlike `tests/e2e/`).
Django is initialized here so tests can use `django.test.Client` and import
project code.
"""

import os

import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "conf.settings")
django.setup()
