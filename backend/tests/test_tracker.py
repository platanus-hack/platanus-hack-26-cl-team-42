"""Unit tests for the celery-tracker integration.

These run in-process via ``django.test.Client`` and exercise:
- Tracker API routes are wired up and return correct HTTP status codes.
- The ``/celery-tasks`` endpoint lists the sample task registered by
  ``apps.demo.tasks``.
- The ``/tracked-tasks`` endpoint returns a list (even if empty).

A live Redis is NOT required because the tracker routes are tested
without dispatching to a broker — only import/URL resolution is verified.
"""

from __future__ import annotations

import pytest
from django.contrib.auth import get_user_model
from django.conf import settings
from django.test import Client


URL = f"/{settings.URL_PREFIX}/api/tracker"
User = get_user_model()


@pytest.fixture()
def auth_client(db):
    """A Django test client authenticated as a superuser."""
    user = User.objects.create_superuser(email="test@example.com", password="pw")
    c = Client()
    c.force_login(user)
    return c


@pytest.mark.django_db
def test_tracker_celery_tasks_endpoint_returns_200(auth_client):
    """The /celery-tasks listing endpoint should be reachable."""
    response = auth_client.get(f"{URL}/celery-tasks")
    assert response.status_code == 200


@pytest.mark.django_db
def test_tracker_celery_tasks_includes_sample_task(auth_client):
    """The sample task registered by apps.demo.tasks should appear in the list."""
    # Import forces Celery task registration even without a running worker.
    import apps.demo.tasks  # noqa: F401

    response = auth_client.get(f"{URL}/celery-tasks")
    assert response.status_code == 200
    names = [t["name"] for t in response.json()]
    assert "demo.tasks.sample_task" in names


@pytest.mark.django_db
def test_tracker_tracked_tasks_endpoint_returns_200_when_no_redis(auth_client, monkeypatch):
    """The /tracked-tasks list endpoint returns 200 even when Redis is absent.

    We stub ``TrackerService.list_trackers`` so no broker connection is made.
    """
    from tracker import service as tracker_service

    monkeypatch.setattr(
        tracker_service.TrackerService,
        "list_trackers",
        lambda self: [],
    )
    response = auth_client.get(f"{URL}/tracked-tasks")
    assert response.status_code == 200
    assert response.json() == []
