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


@pytest.fixture(autouse=True)
def synthesis_jobs(settings, monkeypatch, tmp_path):
    from apps.transcription.tasks import generate_patient_synthesis

    settings.CACHES = {
        **settings.CACHES,
        "patient_summaries": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": str(tmp_path),
        },
    }
    queued = []
    monkeypatch.setattr(
        generate_patient_synthesis, "apply_async", lambda *, args, **kw: queued.append(args)
    )
    return queued
