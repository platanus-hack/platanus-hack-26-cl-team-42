"""Smoke test: the backend's `/-/_health/` endpoint responds OK."""

from __future__ import annotations

import httpx


def test_health_endpoint_returns_ok(client: httpx.Client) -> None:
    response = client.get("/-/_health/")
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload == {"status": "ok"}
