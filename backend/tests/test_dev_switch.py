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
