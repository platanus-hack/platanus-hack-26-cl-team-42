"""Tests for the live eventcore documentation graph.

Covers ``/-/api/eventcore/graph`` (JSON) and ``/-/eventcore-docs/`` (UI).
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

GRAPH_URL = f"/{settings.URL_PREFIX}/api/eventcore/graph"
UI_URL = f"/{settings.URL_PREFIX}/eventcore-docs/"
User = get_user_model()


@pytest.fixture()
def auth_client(db):
    user = User.objects.create_superuser(email="test@example.com", password="pw")
    c = Client()
    c.force_login(user)
    return c


@pytest.fixture(autouse=True)
def _subscribers():
    eventcore.clear()
    eventcore.on(OrderEvent, announce_order_event)
    log_subscribers.register()
    yield
    eventcore.clear()


@pytest.mark.django_db
def test_graph_requires_auth():
    response = Client().get(GRAPH_URL)
    assert response.status_code in {401, 403}


@pytest.mark.django_db
def test_graph_endpoint_returns_demo_wiring(auth_client):
    response = auth_client.get(GRAPH_URL)
    assert response.status_code == 200
    data = response.json()

    nodes = {n["id"]: n for n in data["nodes"]}
    assert "command:PlaceOrder" in nodes
    assert "event:OrderPlaced" in nodes
    assert nodes["command:PlaceOrder"]["applies_events"] == ["OrderPlaced"]
    assert nodes["command:PlaceOrder"]["is_entry"] is True
    assert nodes["command:ShipOrder"]["is_entry"] is False

    applies = {
        (e["source"], e["target"])
        for e in data["edges"]
        if e["kind"] == "applies"
    }
    assert ("command:PlaceOrder", "event:OrderPlaced") in applies

    policy_edges = [e for e in data["edges"] if e["kind"] == "policy"]
    assert any(e["source"] == "event:OrderPlaced" for e in policy_edges)

    assert "demo" in data["flow"]["apps"]
    assert "command:PlaceOrder" in data["flow"]["entry_command_ids"]


@pytest.mark.django_db
def test_docs_ui_requires_login():
    response = Client().get(UI_URL)
    assert response.status_code in {302, 401, 403}


@pytest.mark.django_db
def test_docs_ui_renders_for_authenticated_user(auth_client):
    response = auth_client.get(UI_URL)
    assert response.status_code == 200
    assert b"Eventcore flow graph" in response.content
    assert GRAPH_URL.encode() in response.content or b"/api/eventcore/graph" in response.content
