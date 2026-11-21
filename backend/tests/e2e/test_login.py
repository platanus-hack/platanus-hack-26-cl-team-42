"""E2E test for the seeded local development user.

The dev entrypoint (``backend/docker/entrypoint-dev.sh``) seeds a superuser on
every startup (``test@localhost`` / ``test`` by default). This verifies that
the user exists and can authenticate through the allauth headless API — the
same flow the frontend login form uses.
"""

from __future__ import annotations

import httpx


def test_seeded_dev_user_can_log_in(
    base_url: str, dev_credentials: tuple[str, str]
) -> None:
    email, password = dev_credentials
    with httpx.Client(base_url=base_url, timeout=10.0) as client:
        resp = client.post(
            "/-/.auth/headless/browser/v1/auth/login",
            json={"email": email, "password": password},
        )

    assert resp.status_code == 200, f"login failed ({resp.status_code}): {resp.text}"
    payload = resp.json()
    assert payload["meta"]["is_authenticated"] is True
    assert payload["data"]["user"]["email"] == email
