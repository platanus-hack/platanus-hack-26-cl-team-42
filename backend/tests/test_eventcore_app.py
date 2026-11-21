"""Tests for the eventcore catalog endpoints and the ``eventcore.app`` log.

These cover the pieces layered on top of the demo:
- ``/commands`` and ``/event-types`` expose the eventcore registries.
- ``/log`` exposes the ``LogRecord`` audit trail written by the
  ``eventcore.app`` subscribers (command invocations via ``on(Command, ...)``,
  applied events via ``on(Event, ...)``).
"""

from __future__ import annotations

import pytest
from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import Client

import eventcore
from apps.demo.events import OrderEvent
from apps.demo.policies import announce_order_event
from eventcore.app import subscribers as log_subscribers
from eventcore.app.models import LogRecord

URL = f"/{settings.URL_PREFIX}/api/demo"
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
def _subscribers():
    """Register both the demo and eventcore.app listeners on a clean registry.

    Other test modules clear the process-wide registry, so we re-wire here.
    """
    eventcore.clear()
    eventcore.on(OrderEvent, announce_order_event)
    log_subscribers.register()
    yield
    eventcore.clear()


def _place_order(client, capture):
    with capture(execute=True):
        response = client.post(
            f"{CMD_URL}/PlaceOrder",
            data={"customer_name": "Ada", "item": "Mechanical keyboard"},
            content_type="application/json",
        )
    assert response.status_code == 200, response.content
    return response.json()


@pytest.mark.django_db
def test_commands_endpoint_lists_registered_commands(auth_client):
    response = auth_client.get(f"{URL}/commands")
    assert response.status_code == 200
    commands = {c["name"]: c for c in response.json()}
    assert {"PlaceOrder", "ShipOrder", "CancelOrder"} <= set(commands)

    ship = commands["ShipOrder"]
    assert "CarrierNotSupported" in ship["errors"]
    assert {f["name"] for f in ship["fields"]} >= {"order_id", "carrier_name"}


@pytest.mark.django_db
def test_event_types_endpoint_lists_registered_events(auth_client):
    response = auth_client.get(f"{URL}/event-types")
    assert response.status_code == 200
    events = {e["name"]: e for e in response.json()}
    assert {"OrderPlaced", "OrderShipped", "OrderCancelled"} <= set(events)
    assert events["OrderShipped"]["target_model"] == "Order"


@pytest.mark.django_db
def test_invoking_a_command_writes_command_and_event_log_records(
    auth_client, django_capture_on_commit_callbacks
):
    _place_order(auth_client, django_capture_on_commit_callbacks)

    records = set(LogRecord.objects.values_list("kind", "name"))
    assert ("command", "PlaceOrder") in records
    assert ("event", "OrderPlaced") in records


@pytest.mark.django_db
def test_command_and_its_events_share_correlation_id(
    auth_client, django_capture_on_commit_callbacks
):
    _place_order(auth_client, django_capture_on_commit_callbacks)

    command = LogRecord.objects.get(kind="command", name="PlaceOrder")
    event = LogRecord.objects.get(kind="event", name="OrderPlaced")
    assert command.correlation_id
    assert command.correlation_id == event.correlation_id


@pytest.mark.django_db
def test_log_endpoint_filters_by_kind(auth_client, django_capture_on_commit_callbacks):
    _place_order(auth_client, django_capture_on_commit_callbacks)

    response = auth_client.get(f"{URL}/log", {"kind": "command"})
    assert response.status_code == 200
    data = response.json()
    assert len(data) >= 1
    assert all(r["kind"] == "command" for r in data)
    assert any(r["name"] == "PlaceOrder" for r in data)
