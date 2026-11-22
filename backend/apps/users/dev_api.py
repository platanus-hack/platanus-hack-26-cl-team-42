"""Cambio rápido entre cuentas de prueba, para recorrer la app como cada profesional.

Hay dos formas de habilitarlo, y ninguna deja cambiar de cuenta a un visitante anónimo:

- desarrollo: ``DEBUG`` y ``DEMO_ACCOUNT_SWITCH_ENABLED``, desde una cuenta ``@localhost``;
- demo desplegada: ``DEMO_SUPERUSER_SWITCH_ENABLED``, solo para quien inició sesión como
  superusuario. Al pasar a otra cuenta la sesión recuerda al superusuario (``OPERATOR_KEY``,
  que solo escribe el servidor), así que puede volver a su cuenta y a cualquier otra.
"""

from django.conf import settings
from django.contrib.auth import get_user_model, login
from django.db.models.functions import Lower
from ninja import Router, Schema
from ninja.errors import HttpError

router = Router(tags=["dev"])
DEMO_DOMAIN = "@localhost"
LOGIN_BACKEND = "django.contrib.auth.backends.ModelBackend"


OPERATOR_KEY = "demo_operator_id"


class DemoAccount(Schema):
    email: str
    name: str
    profession: str
    current: bool
    # El superusuario que opera la demo (su propia cuenta, para poder volver a ella).
    operator: bool = False


class SwitchIn(Schema):
    email: str


@router.get("/accounts", response=list[DemoAccount])
def list_demo_accounts(request):
    """Cuentas a las que esta sesión puede cambiarse."""
    return [_out(request, user) for user in _switchable(request)]


@router.post("/switch", response=DemoAccount)
def switch_demo_account(request, data: SwitchIn):
    """Inicia sesión como una cuenta de prueba (nunca como una cuenta ajena a la demo)."""
    email = data.email.strip()
    target = next((u for u in _switchable(request) if u.email.casefold() == email.casefold()), None)
    if target is None:
        raise HttpError(404, "No existe esa cuenta de demo.")
    operator = _operator(request)
    login(request, target, backend=LOGIN_BACKEND)  # cambiar de usuario vacía la sesión
    if operator is not None and target.pk != operator.pk:
        request.session[OPERATOR_KEY] = operator.pk
    return _out(request, target)


def _switchable(request) -> list:
    """Quién se puede elegir: las cuentas de demo y, si hay un superusuario, su propia cuenta."""
    operator = _operator(request)
    if operator is not None:
        accounts = list(_demo_accounts().order_by("id"))
        return [operator, *accounts]
    if _dev_switch_allowed(request.user):
        return list(_demo_accounts().order_by("id"))
    return []


def _operator(request):
    """El superusuario detrás de la sesión (él mismo, o quien pasó a una cuenta de demo)."""
    if not settings.DEMO_SUPERUSER_SWITCH_ENABLED:
        return None
    user = request.user
    if user.is_authenticated and user.is_superuser:
        return user
    operator_id = request.session.get(OPERATOR_KEY)
    if operator_id is None:
        return None
    return (
        get_user_model().objects.filter(pk=operator_id, is_active=True, is_superuser=True).first()
    )


def _dev_switch_allowed(user) -> bool:
    return (
        settings.DEBUG
        and settings.DEMO_ACCOUNT_SWITCH_ENABLED
        and user.is_authenticated
        and user.email.casefold().endswith(DEMO_DOMAIN)
    )


def _out(request, user) -> DemoAccount:
    operator = _operator(request)
    return DemoAccount(
        email=user.email,
        name=user.name,
        profession=user.profession,
        current=user.pk == request.user.pk,
        operator=operator is not None and user.pk == operator.pk,
    )


def _demo_accounts():
    accounts = get_user_model().objects.filter(
        email__iendswith=DEMO_DOMAIN, is_active=True, is_staff=False, is_superuser=False
    )
    # Con una lista configurada solo se ofrecen esas cuentas (el resto de la base no se toca).
    allowed = [email.strip().casefold() for email in settings.DEMO_SWITCH_EMAILS if email.strip()]
    if allowed:
        accounts = accounts.annotate(lowered=Lower("email")).filter(lowered__in=allowed)
    return accounts
