"""Turnos: la app sabe qué profesionales están de turno y cuáles no.

Un profesional sin ningún turno vigente está fuera de turno. Los turnos los carga la
institución (admin de Django o su sistema de turnos); aquí solo se consultan.
"""

from datetime import datetime, timedelta

from django.contrib.auth import get_user_model
from django.utils import timezone

from .models import Shift


def is_on_shift(user, at: datetime | None = None) -> bool:
    at = at or timezone.now()
    return Shift.objects.filter(user=user, starts_at__lte=at, ends_at__gt=at).exists()


def users_on_shift(profession: str | None = None, at: datetime | None = None):
    """Profesionales de turno ahora (opcionalmente de una categoría)."""
    at = at or timezone.now()
    users = get_user_model().objects.filter(
        is_active=True, shifts__starts_at__lte=at, shifts__ends_at__gt=at
    )
    if profession:
        users = users.filter(profession=profession)
    return users.distinct()


def start_shift(user, hours: int = 8) -> Shift:
    """Pone al profesional de turno desde ahora (para demos y pruebas)."""
    end_shift(user)
    now = timezone.now()
    return Shift.objects.create(
        user=user, starts_at=now - timedelta(hours=1), ends_at=now + timedelta(hours=hours)
    )


def end_shift(user) -> None:
    """Termina los turnos vigentes del profesional: queda fuera de turno."""
    now = timezone.now()
    Shift.objects.filter(user=user, starts_at__lte=now, ends_at__gt=now).update(ends_at=now)
