"""Cambio rápido entre cuentas de demo, solo en desarrollo (``DEBUG``), montado en ``/-/api/dev``.

Sirve para probar flujos entre varios profesionales (p. ej. un conflicto entre dos informes)
sin cerrar sesión y volver a entrar. Solo permite cuentas de demo (correo ``@localhost``).
"""

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
    """Cuentas de demo disponibles para cambiar de usuario (vacío fuera de desarrollo)."""
    if not settings.DEBUG:
        return []
    users = get_user_model().objects.filter(email__endswith=DEMO_DOMAIN, is_active=True)
    return [
        DemoAccount(
            email=user.email,
            name=user.name,
            profession=user.profession,
            current=user.pk == request.user.pk,
        )
        for user in users.order_by("id")
    ]


@router.post("/switch", response=DemoAccount)
def switch_demo_account(request, data: SwitchIn):
    """Inicia sesión como otra cuenta de demo (sin clave), solo con ``DEBUG``."""
    if not settings.DEBUG:
        raise HttpError(404, "No disponible.")
    user = (
        get_user_model()
        .objects.filter(
            email__iexact=data.email.strip(), email__endswith=DEMO_DOMAIN, is_active=True
        )
        .first()
    )
    if user is None:
        raise HttpError(404, "No existe esa cuenta de demo.")
    login(request, user, backend=LOGIN_BACKEND)
    return DemoAccount(email=user.email, name=user.name, profession=user.profession, current=True)
