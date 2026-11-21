"""Unit tests for the eventcore demo app.

Write operations (place/ship/cancel) now go through the generic command API
at ``/-/api/commands/<CommandName>``.  Read-only endpoints remain on the
Ninja router at ``/-/api/demo/…``.
"""

from __future__ import annotations

import logging

import pytest
from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import Client

import eventcore
from apps.demo.events import OrderEvent
from apps.demo.models import Order
from apps.demo.policies import announce_order_event

DEMO_URL = f"/{settings.URL_PREFIX}/api/demo"
CMD_URL = f"/{settings.URL_PREFIX}/api/commands"
User = get_user_model()


@pytest.fixture()
def auth_client(db):
    """A Django test client authenticated as a superuser."""
    user = User.objects.create_superuser(email="test@example.com", password="pw")
    c = Client()
    c.force_login(user)
    return c


@pytest.fixture(autouse=True)
def _demo_policies():
    """Wire the demo's event policy on a clean registry."""
    eventcore.clear()
    eventcore.on(OrderEvent, announce_order_event)


def _place_order(client, capture, customer_name="Ada", item="Mechanical keyboard"):
    with capture(execute=True):
        response = client.post(
            f"{CMD_URL}/PlaceOrder",
            data={"customer_name": customer_name, "item": item},
            content_type="application/json",
        )
    assert response.status_code == 200, response.content
    return response.json()["result"]


@pytest.mark.django_db
def test_place_order_creates_pending_order(auth_client, django_capture_on_commit_callbacks):
    order = _place_order(auth_client, django_capture_on_commit_callbacks)
    assert order["status"] == "pending"
    assert Order.objects.filter(pk=order["id"], status="pending").exists()


@pytest.mark.django_db
def test_place_order_runs_lifecycle_policy(
    auth_client, django_capture_on_commit_callbacks, caplog
):
    with caplog.at_level(logging.INFO, logger="apps.demo.policies"):
        _place_order(auth_client, django_capture_on_commit_callbacks)
    assert any("OrderPlaced" in message for message in caplog.messages)


@pytest.mark.django_db
def test_ship_order_transitions_to_shipped(auth_client, django_capture_on_commit_callbacks):
    order = _place_order(auth_client, django_capture_on_commit_callbacks)

    with django_capture_on_commit_callbacks(execute=True):
        response = auth_client.post(
            f"{CMD_URL}/ShipOrder",
            data={"order_id": order["id"], "carrier_name": "ups"},
            content_type="application/json",
        )
    assert response.status_code == 200, response.content
    shipped = response.json()["result"]
    assert shipped["status"] == "shipped"
    assert shipped["carrier_name"] == "ups"
    assert shipped["shipped_at"] is not None


@pytest.mark.django_db
def test_ship_order_rejects_unsupported_carrier(auth_client, django_capture_on_commit_callbacks):
    order = _place_order(auth_client, django_capture_on_commit_callbacks)

    response = auth_client.post(
        f"{CMD_URL}/ShipOrder",
        data={"order_id": order["id"], "carrier_name": "pigeon"},
        content_type="application/json",
    )
    assert response.status_code == 409
    assert response.json()["error"] == "CarrierNotSupported"


@pytest.mark.django_db
def test_ship_order_rejects_non_pending_order(auth_client, django_capture_on_commit_callbacks):
    order = _place_order(auth_client, django_capture_on_commit_callbacks)
    with django_capture_on_commit_callbacks(execute=True):
        auth_client.post(
            f"{CMD_URL}/CancelOrder",
            data={"order_id": order["id"], "reason": "changed my mind"},
            content_type="application/json",
        )

    response = auth_client.post(
        f"{CMD_URL}/ShipOrder",
        data={"order_id": order["id"], "carrier_name": "ups"},
        content_type="application/json",
    )
    assert response.status_code == 409
    assert response.json()["error"] == "NotPending"


@pytest.mark.django_db
def test_ship_order_missing_order_returns_404(auth_client):
    response = auth_client.post(
        f"{CMD_URL}/ShipOrder",
        data={"order_id": 999999, "carrier_name": "ups"},
        content_type="application/json",
    )
    assert response.status_code == 404
    assert response.json()["error"] == "OrderNotFound"


@pytest.mark.django_db
def test_cancel_order_records_reason(auth_client, django_capture_on_commit_callbacks):
    order = _place_order(auth_client, django_capture_on_commit_callbacks)

    with django_capture_on_commit_callbacks(execute=True):
        response = auth_client.post(
            f"{CMD_URL}/CancelOrder",
            data={"order_id": order["id"], "reason": "changed my mind"},
            content_type="application/json",
        )
    assert response.status_code == 200, response.content
    cancelled = response.json()["result"]
    assert cancelled["status"] == "cancelled"
    assert cancelled["cancel_reason"] == "changed my mind"


@pytest.mark.django_db
def test_carriers_endpoint_lists_supported_carriers(auth_client):
    response = auth_client.get(f"{DEMO_URL}/carriers")
    assert response.status_code == 200
    assert "ups" in response.json()


@pytest.mark.django_db
def test_order_statuses_are_localized(auth_client):
    """The /order-statuses labels are translated per Accept-Language."""
    english = auth_client.get(f"{DEMO_URL}/order-statuses", HTTP_ACCEPT_LANGUAGE="en")
    spanish = auth_client.get(f"{DEMO_URL}/order-statuses", HTTP_ACCEPT_LANGUAGE="es")
    en_labels = {row["value"]: row["label"] for row in english.json()}
    es_labels = {row["value"]: row["label"] for row in spanish.json()}
    assert en_labels["pending"] == "Pending"
    assert es_labels["pending"] == "Pendiente"
    assert es_labels["shipped"] == "Enviado"


@pytest.mark.django_db
def test_command_error_detail_is_localized(auth_client):
    """LocaleMiddleware honours Accept-Language, so error detail is translated."""
    english = auth_client.post(
        f"{CMD_URL}/ShipOrder",
        data={"order_id": 999999, "carrier_name": "ups"},
        content_type="application/json",
        HTTP_ACCEPT_LANGUAGE="en",
    )
    spanish = auth_client.post(
        f"{CMD_URL}/ShipOrder",
        data={"order_id": 999999, "carrier_name": "ups"},
        content_type="application/json",
        HTTP_ACCEPT_LANGUAGE="es",
    )
    # The machine-readable error code stays stable across languages...
    assert english.json()["error"] == spanish.json()["error"] == "OrderNotFound"
    # ...while the human-readable detail is localized.
    assert english.json()["detail"] == "Order 999999 not found"
    assert spanish.json()["detail"] == "No se encontró el pedido 999999"
