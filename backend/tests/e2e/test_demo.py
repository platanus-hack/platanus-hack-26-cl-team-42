"""E2E tests for the eventcore demo (orders).

These run against the *live* docker-compose stack (``just up`` first) and
exercise the full place → ship flow through the generic command API
(``/-/api/commands/``), including the eventcore.app audit log written after
commit. The demo Ninja API (``/-/api/demo/``) itself is read-only.
"""

from __future__ import annotations

import httpx

URL_PREFIX = "/-"
COMMANDS = f"{URL_PREFIX}/api/commands"
DEMO_API = f"{URL_PREFIX}/api/demo"


def test_demo_place_and_ship_order(authenticated_client: httpx.Client) -> None:
    """Place an order, ship it, and verify the event log recorded both events."""
    place_resp = authenticated_client.post(
        f"{COMMANDS}/PlaceOrder",
        json={"customer_name": "E2E Tester", "item": "Rubber duck"},
    )
    assert place_resp.status_code == 200, place_resp.text
    placed = place_resp.json()
    assert placed["command"] == "PlaceOrder"
    order = placed["result"]
    assert order["status"] == "pending"

    ship_resp = authenticated_client.post(
        f"{COMMANDS}/ShipOrder",
        json={"order_id": order["id"], "carrier_name": "ups"},
    )
    assert ship_resp.status_code == 200, ship_resp.text
    shipped = ship_resp.json()["result"]
    assert shipped["status"] == "shipped"
    assert shipped["carrier_name"] == "ups"

    log_resp = authenticated_client.get(f"{DEMO_API}/log", params={"kind": "event"})
    assert log_resp.status_code == 200, log_resp.text
    event_names = {r["name"] for r in log_resp.json()}
    assert {"OrderPlaced", "OrderShipped"} <= event_names


def test_demo_command_errors_map_to_http(authenticated_client: httpx.Client) -> None:
    """Domain failures surface as 404/409 with the CommandError class name."""
    missing = authenticated_client.post(
        f"{COMMANDS}/ShipOrder",
        json={"order_id": 999999, "carrier_name": "ups"},
    )
    assert missing.status_code == 404, missing.text
    assert missing.json()["error"] == "OrderNotFound"

    place_resp = authenticated_client.post(
        f"{COMMANDS}/PlaceOrder",
        json={"customer_name": "E2E Tester", "item": "Unshippable anvil"},
    )
    assert place_resp.status_code == 200, place_resp.text
    order_id = place_resp.json()["result"]["id"]

    bad_carrier = authenticated_client.post(
        f"{COMMANDS}/ShipOrder",
        json={"order_id": order_id, "carrier_name": "pigeon"},
    )
    assert bad_carrier.status_code == 409, bad_carrier.text
    assert bad_carrier.json()["error"] == "CarrierNotSupported"
