"""Smoke tests for the URL configuration and health endpoint.

These run in-process via `django.test.Client` — they exercise the middleware
stack and URLconf without needing a database or a running server.
"""

from django.conf import settings
from django.test import Client


def test_health_endpoint_returns_ok():
    response = Client().get(f"/{settings.URL_PREFIX}/_health/")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
