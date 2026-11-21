"""Backend unit test fixtures.

Unit tests run in-process (no running server required, unlike `tests/e2e/`).
Django is initialized here so tests can use `django.test.Client` and import
project code.
"""

import os

import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "conf.settings")
django.setup()


import pytest  # noqa: E402


@pytest.fixture(autouse=True)
def isolated_pipeline_cache(tmp_path, monkeypatch):
    """Los tests nunca leen ni escriben la caché real del pipeline (samples/cache)."""
    monkeypatch.setenv("PIPELINE_CACHE_DIR", str(tmp_path / "pipeline-cache"))
