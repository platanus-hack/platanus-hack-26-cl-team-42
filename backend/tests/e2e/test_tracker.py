"""E2E tests for the celery-tracker integration.

These tests run against the *live* docker-compose stack (``just up`` first).
They require Redis and the Celery worker service to be running.
"""

from __future__ import annotations

import time

import httpx


URL_PREFIX = "/-"


def test_tracker_celery_tasks_lists_sample_task(authenticated_client: httpx.Client) -> None:
    """The /celery-tasks endpoint should list the sample task."""
    response = authenticated_client.get(f"{URL_PREFIX}/api/tracker/celery-tasks")
    assert response.status_code == 200, response.text
    names = [t["name"] for t in response.json()]
    assert "demo.tasks.sample_task" in names


def test_tracker_tracked_tasks_empty_initially(authenticated_client: httpx.Client) -> None:
    """The /tracked-tasks list should respond 200 (may be empty or have entries)."""
    response = authenticated_client.get(f"{URL_PREFIX}/api/tracker/tracked-tasks")
    assert response.status_code == 200, response.text
    assert isinstance(response.json(), list)


def test_tracker_run_and_poll_sample_task(authenticated_client: httpx.Client) -> None:
    """Dispatch the sample task through the API and poll until it completes."""
    # Dispatch
    run_resp = authenticated_client.post(
        f"{URL_PREFIX}/api/tracker/celery-tasks/demo.tasks.sample_task/run",
        json={"args": [], "kwargs": {"steps": 2, "step_duration": 0.05}},
    )
    assert run_resp.status_code == 200, run_resp.text
    payload = run_resp.json()
    assert "tracker_id" in payload
    tracker_id = payload["tracker_id"]

    # Poll for up to 15 seconds
    deadline = time.time() + 15
    terminal_states = {"completed", "failed", "cancelled"}
    final_status = None

    while time.time() < deadline:
        detail_resp = authenticated_client.get(
            f"{URL_PREFIX}/api/tracker/tracked-tasks/{tracker_id}"
        )
        assert detail_resp.status_code == 200, detail_resp.text
        detail = detail_resp.json()
        final_status = detail.get("status")
        if final_status in terminal_states:
            break
        time.sleep(0.5)

    assert final_status == "completed", (
        f"Expected task to complete within 15s, got status={final_status!r}"
    )
