"""Cambio de cuenta de demo (solo en desarrollo)."""

import pytest
from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import Client

API = f"/{settings.URL_PREFIX}/api/dev"
User = get_user_model()


@pytest.fixture()
def accounts(db):
    return (
        User.objects.create_user(email="test@localhost", password="pw"),
        User.objects.create_user(email="enfermeria@localhost", password="pw", name="EU Soto"),
        User.objects.create_user(email="real@clinic.cl", password="pw"),
    )


def test_switch_lists_only_demo_accounts_and_changes_the_session(settings, accounts):
    settings.DEBUG = True
    client = Client()
    client.force_login(accounts[0])

    listed = client.get(f"{API}/accounts").json()
    switched = client.post(
        f"{API}/switch", {"email": "enfermeria@localhost"}, content_type="application/json"
    )

    assert [a["email"] for a in listed] == ["test@localhost", "enfermeria@localhost"]
    assert [a["current"] for a in listed] == [True, False]
    assert switched.status_code == 200
    assert client.get(f"{API}/accounts").json()[1]["current"] is True


def test_switch_refuses_real_accounts_and_production(settings, accounts):
    client = Client()
    client.force_login(accounts[0])
    settings.DEBUG = True
    as_real = client.post(
        f"{API}/switch", {"email": "real@clinic.cl"}, content_type="application/json"
    )
    settings.DEBUG = False
    in_prod = client.post(
        f"{API}/switch", {"email": "enfermeria@localhost"}, content_type="application/json"
    )

    assert as_real.status_code == 404
    assert in_prod.status_code == 404
    assert client.get(f"{API}/accounts").json() == []
