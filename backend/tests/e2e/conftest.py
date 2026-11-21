"""Backend end-to-end test fixtures.

These tests run *against* a running backend (via the `local/` docker-compose
stack), not against an in-process Django test client. The base URL defaults to
the in-cluster service name (`http://backend:8000`) when the test process is
itself inside a compose container, and falls back to `http://localhost:8000`
otherwise. Override with the `BACKEND_E2E_BASE_URL` environment variable.
"""

from __future__ import annotations

import os
import socket

import httpx
import pytest


def _default_base_url() -> str:
    # When running inside the compose network the `backend` service is reachable
    # by name on the internal port. From the host (`localhost:8000` is published
    # in docker-compose.yml) we hit the published port instead.
    try:
        socket.gethostbyname("backend")
        return "http://backend:8000"
    except OSError:
        return "http://localhost:8000"


@pytest.fixture(scope="session")
def base_url() -> str:
    return os.environ.get("BACKEND_E2E_BASE_URL") or _default_base_url()


@pytest.fixture(scope="session")
def client(base_url: str) -> httpx.Client:
    with httpx.Client(base_url=base_url, timeout=10.0) as session:
        yield session


@pytest.fixture(scope="session")
def dev_credentials() -> tuple[str, str]:
    """Credentials of the user seeded by the backend dev entrypoint.

    Defaults match the entrypoint defaults; override with the
    DJANGO_SUPERUSER_EMAIL / DJANGO_SUPERUSER_PASSWORD env vars.
    """
    return (
        os.environ.get("DJANGO_SUPERUSER_EMAIL", "test@localhost"),
        os.environ.get("DJANGO_SUPERUSER_PASSWORD", "test"),
    )


@pytest.fixture(scope="session")
def authenticated_client(
    base_url: str, dev_credentials: tuple[str, str]
) -> httpx.Client:
    """An httpx.Client with a valid Django session cookie.

    Logs in once using the allauth headless browser API and the superuser
    credentials seeded by the backend entrypoint.
    """
    email, password = dev_credentials
    with httpx.Client(base_url=base_url, timeout=10.0) as session:
        resp = session.post(
            "/-/.auth/headless/browser/v1/auth/login",
            json={"email": email, "password": password},
        )
        assert resp.status_code == 200, (
            f"e2e login failed ({resp.status_code}): {resp.text}"
        )
        yield session
