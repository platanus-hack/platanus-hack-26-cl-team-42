"""Cambio rápido entre cuentas de prueba en entornos de desarrollo habilitados."""

from django.conf import settings
from django.contrib.auth import get_user_model, login
from ninja import Router, Schema
from ninja.errors import HttpError

router = Router(tags=["dev"])
DEMO_DOMAIN = "@localhost"
LOGIN_BACKEND = "django.contrib.auth.backends.ModelBackend"


class DemoAccount(Schema):
    email: str
    name: str
    profession: str
    current: bool


class SwitchIn(Schema):
    email: str


@router.get("/accounts", response=list[DemoAccount])
def list_demo_accounts(request):
    """Cuentas de prueba disponibles en esta sesión."""
    if not _can_switch(request.user):
        return []
    return [
        DemoAccount(
            email=user.email,
            name=user.name,
            profession=user.profession,
            current=user.pk == request.user.pk,
        )
        for user in _demo_accounts().order_by("id")
    ]


@router.post("/switch", response=DemoAccount)
def switch_demo_account(request, data: SwitchIn):
    """Inicia sesión como una cuenta de prueba sin acceso administrativo."""
    if not _can_switch(request.user):
        raise HttpError(404, "No disponible.")
    user = _demo_accounts().filter(email__iexact=data.email.strip()).first()
    if user is None:
        raise HttpError(404, "No existe esa cuenta de demo.")
    login(request, user, backend=LOGIN_BACKEND)
    return DemoAccount(email=user.email, name=user.name, profession=user.profession, current=True)


def _can_switch(user) -> bool:
    return (
        settings.DEBUG
        and settings.DEMO_ACCOUNT_SWITCH_ENABLED
        and user.email.casefold().endswith(DEMO_DOMAIN)
    )


def _demo_accounts():
    return get_user_model().objects.filter(
        email__iendswith=DEMO_DOMAIN, is_active=True, is_staff=False, is_superuser=False
    )
