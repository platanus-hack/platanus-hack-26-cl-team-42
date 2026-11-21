"""Tests for the generic command API (``/-/api/commands/``).

These exercise the registry-driven DRF routing mechanism itself:
- the index lists all registered commands,
- the per-command POST validates fields and returns the result envelope,
- domain failures (CommandError) map to 404 / 409,
- missing required fields return 400.
"""

from __future__ import annotations

import pytest
from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import Client

import eventcore
from apps.demo.events import OrderEvent
from apps.demo.models import Order
from apps.demo.policies import announce_order_event

URL = f"/{settings.URL_PREFIX}/api/commands"
User = get_user_model()


@pytest.fixture()
def auth_client(db):
    user = User.objects.create_superuser(email="cmd-test@example.com", password="pw")
    c = Client()
    c.force_login(user)
    return c


@pytest.fixture(autouse=True)
def _demo_policies():
    eventcore.clear()
    eventcore.on(OrderEvent, announce_order_event)


# ---------------------------------------------------------------------------
# Index
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_index_lists_registered_commands(auth_client):
    response = auth_client.get(f"{URL}/")
    assert response.status_code == 200
    names = [cmd["name"] for cmd in response.json()]
    assert "PlaceOrder" in names
    assert "ShipOrder" in names
    assert "CancelOrder" in names


@pytest.mark.django_db
def test_index_includes_fields_and_errors(auth_client):
    response = auth_client.get(f"{URL}/")
    commands = {cmd["name"]: cmd for cmd in response.json()}
    ship = commands["ShipOrder"]
    assert any(f["name"] == "order_id" for f in ship["fields"])
    assert any(f["name"] == "carrier_name" for f in ship["fields"])
    assert "OrderNotFound" in ship["errors"]
    assert "CarrierNotSupported" in ship["errors"]


# ---------------------------------------------------------------------------
# GET on individual command
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_command_detail_get_returns_metadata(auth_client):
    response = auth_client.get(f"{URL}/PlaceOrder")
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "PlaceOrder"
    assert any(f["name"] == "customer_name" for f in data["fields"])


# ---------------------------------------------------------------------------
# Successful submission
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_place_order_returns_envelope(auth_client, django_capture_on_commit_callbacks):
    with django_capture_on_commit_callbacks(execute=True):
        response = auth_client.post(
            f"{URL}/PlaceOrder",
            data={"customer_name": "Ada", "item": "Keyboard"},
            content_type="application/json",
        )
    assert response.status_code == 200
    body = response.json()
    assert body["command"] == "PlaceOrder"
    assert body["correlation_id"] is not None
    assert body["result"]["status"] == "pending"
    assert Order.objects.filter(pk=body["result"]["id"]).exists()


# ---------------------------------------------------------------------------
# Validation errors
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_missing_required_field_returns_400(auth_client):
    # PlaceOrder requires both customer_name and item
    response = auth_client.post(
        f"{URL}/PlaceOrder",
        data={"customer_name": "Ada"},
        content_type="application/json",
    )
    assert response.status_code == 400


@pytest.mark.django_db
def test_unknown_command_returns_404(auth_client):
    response = auth_client.post(
        f"{URL}/NonExistentCommand",
        data={},
        content_type="application/json",
    )
    assert response.status_code == 404


# ---------------------------------------------------------------------------
# Domain failures
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_command_error_not_found_returns_404(auth_client):
    response = auth_client.post(
        f"{URL}/ShipOrder",
        data={"order_id": 999999, "carrier_name": "ups"},
        content_type="application/json",
    )
    assert response.status_code == 404
    assert response.json()["error"] == "OrderNotFound"


@pytest.mark.django_db
def test_command_error_conflict_returns_409(auth_client, django_capture_on_commit_callbacks):
    with django_capture_on_commit_callbacks(execute=True):
        place = auth_client.post(
            f"{URL}/PlaceOrder",
            data={"customer_name": "Ada", "item": "Keyboard"},
            content_type="application/json",
        )
    order_id = place.json()["result"]["id"]

    response = auth_client.post(
        f"{URL}/ShipOrder",
        data={"order_id": order_id, "carrier_name": "pigeon"},
        content_type="application/json",
    )
    assert response.status_code == 409
    assert response.json()["error"] == "CarrierNotSupported"


# ---------------------------------------------------------------------------
# Unauthenticated access
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_unauthenticated_request_is_rejected(db):
    client = Client()
    response = client.get(f"{URL}/")
    assert response.status_code == 403
