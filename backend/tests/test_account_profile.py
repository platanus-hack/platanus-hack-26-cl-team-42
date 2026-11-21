import pytest
from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import Client
from django.urls import reverse

API = f"/{settings.URL_PREFIX}/api/users/me"


@pytest.mark.django_db
@pytest.mark.parametrize("is_staff", [False, True])
def test_profile_shows_admin_access_independently_of_profession(is_staff):
    user = get_user_model().objects.create_user(
        email="medico@example.com", name="Dra. Vega", profession="medico", is_staff=is_staff
    )
    client = Client()
    client.force_login(user)

    response = client.get(API)

    assert response.status_code == 200
    assert response.json() == {
        "name": "Dra. Vega",
        "email": "medico@example.com",
        "profession": "medico",
        "admin_url": reverse("admin:index") if is_staff else None,
    }


def test_profile_requires_login():
    assert Client().get(API).status_code == 401
