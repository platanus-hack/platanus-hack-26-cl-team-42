"""``rotate_demo_passwords`` deja las cuentas de demo sin su clave conocida."""

from io import StringIO

import pytest
from django.contrib.auth import get_user_model
from django.core.management import call_command

User = get_user_model()


@pytest.mark.django_db
def test_rotates_only_demo_accounts_and_prints_new_passwords():
    demo = User.objects.create_user(email="medico@localhost", password="test")
    outside = User.objects.create_user(email="real@hospital.cl", password="keep")
    out = StringIO()

    call_command("rotate_demo_passwords", stdout=out)

    demo.refresh_from_db()
    outside.refresh_from_db()
    assert not demo.check_password("test")
    assert outside.check_password("keep")
    printed = next(line for line in out.getvalue().splitlines() if "medico@localhost" in line)
    assert demo.check_password(printed.split()[-1])
