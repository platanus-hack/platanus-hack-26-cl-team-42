"""Cambio de cuenta de demo (en desarrollo, o para el superusuario de la demo desplegada)."""

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
        User.objects.create_user(email="staff@localhost", password="pw", is_staff=True),
        User.objects.create_superuser(email="admin@localhost", password="pw"),
    )


def test_switch_lists_only_demo_accounts_and_changes_the_session(settings, accounts):
    settings.DEBUG = True
    settings.DEMO_ACCOUNT_SWITCH_ENABLED = True
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


@pytest.mark.parametrize("target", ["real@clinic.cl", "staff@localhost", "admin@localhost"])
def test_switch_refuses_real_and_privileged_accounts(settings, accounts, target):
    settings.DEBUG = True
    settings.DEMO_ACCOUNT_SWITCH_ENABLED = True
    client = Client()
    client.force_login(accounts[0])

    response = client.post(f"{API}/switch", {"email": target}, content_type="application/json")

    assert response.status_code == 404
    assert client.session["_auth_user_id"] == str(accounts[0].pk)


@pytest.mark.parametrize(
    ("debug", "enabled", "account"), [(False, True, 0), (True, False, 0), (True, True, 2)]
)
def test_switch_requires_an_opted_in_demo_session(settings, accounts, debug, enabled, account):
    settings.DEBUG = debug
    settings.DEMO_ACCOUNT_SWITCH_ENABLED = enabled
    client = Client()
    client.force_login(accounts[account])

    response = client.post(
        f"{API}/switch", {"email": "enfermeria@localhost"}, content_type="application/json"
    )

    assert response.status_code == 404
    assert client.get(f"{API}/accounts").json() == []


@pytest.fixture()
def deployed(settings):
    """La demo desplegada: sin DEBUG ni cambio de desarrollo, solo el del superusuario."""
    settings.DEBUG = False
    settings.DEMO_ACCOUNT_SWITCH_ENABLED = False
    settings.DEMO_SUPERUSER_SWITCH_ENABLED = True


def _switch(client, email):
    return client.post(f"{API}/switch", {"email": email}, content_type="application/json")


def test_the_superuser_switches_between_demo_accounts_and_back(deployed, accounts):
    client = Client()
    client.force_login(accounts[4])

    listed = client.get(f"{API}/accounts").json()
    assert [(a["email"], a["operator"]) for a in listed] == [
        ("admin@localhost", True),
        ("test@localhost", False),
        ("enfermeria@localhost", False),
    ]
    assert _switch(client, "enfermeria@localhost").status_code == 200
    assert client.session["_auth_user_id"] == str(accounts[1].pk)
    # Ya como enfermería, la sesión recuerda al superusuario: ve las cuentas y puede volver.
    again = client.get(f"{API}/accounts").json()
    assert [a["email"] for a in again] == [
        "admin@localhost",
        "test@localhost",
        "enfermeria@localhost",
    ]
    assert _switch(client, "admin@localhost").status_code == 200
    assert client.session["_auth_user_id"] == str(accounts[4].pk)


@pytest.mark.parametrize("account", [0, 2, 3])
def test_only_a_superuser_session_can_switch_when_deployed(deployed, accounts, account):
    client = Client()
    client.force_login(accounts[account])

    assert client.get(f"{API}/accounts").json() == []
    assert _switch(client, "enfermeria@localhost").status_code == 404


def test_an_anonymous_visitor_cannot_switch(deployed, accounts):
    client = Client()

    assert client.get(f"{API}/accounts").status_code == 401
    assert _switch(client, "enfermeria@localhost").status_code == 401


def test_the_superuser_switch_is_off_unless_enabled(settings, deployed, accounts):
    settings.DEMO_SUPERUSER_SWITCH_ENABLED = False
    client = Client()
    client.force_login(accounts[4])

    assert client.get(f"{API}/accounts").json() == []


def test_superuser_cannot_switch_to_real_or_staff_accounts(deployed, accounts):
    client = Client()
    client.force_login(accounts[4])

    assert _switch(client, "real@clinic.cl").status_code == 404
    assert _switch(client, "staff@localhost").status_code == 404
    assert client.session["_auth_user_id"] == str(accounts[4].pk)


def test_losing_superuser_status_ends_the_remembered_operator(deployed, accounts):
    client = Client()
    client.force_login(accounts[4])
    _switch(client, "enfermeria@localhost")
    User.objects.filter(pk=accounts[4].pk).update(is_superuser=False)

    assert client.get(f"{API}/accounts").json() == []


def test_a_configured_email_list_limits_the_accounts_offered(settings, deployed, accounts):
    settings.DEMO_SWITCH_EMAILS = ["Enfermeria@localhost"]
    client = Client()
    client.force_login(accounts[4])

    listed = client.get(f"{API}/accounts").json()

    assert [a["email"] for a in listed] == ["admin@localhost", "enfermeria@localhost"]
    assert _switch(client, "test@localhost").status_code == 404
    assert _switch(client, "enfermeria@localhost").status_code == 200
