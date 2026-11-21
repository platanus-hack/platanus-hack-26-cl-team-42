"""Pone a un profesional de turno o fuera de turno, para probar la reconciliación.

    manage.py set_demo_shift enfermeria@localhost off     # termina su turno ahora
    manage.py set_demo_shift enfermeria@localhost on      # lo pone de turno por 12 horas

Mientras un profesional está fuera de turno no participa de las resoluciones de conflictos y el
otro puede decidir solo. En producción los turnos los carga la institución (admin de Django).
"""

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

from apps.users import shifts


class Command(BaseCommand):
    help = "Pone a un profesional de turno (on) o fuera de turno (off)."

    def add_arguments(self, parser):
        parser.add_argument("email")
        parser.add_argument("state", choices=["on", "off"])

    def handle(self, *args, email: str, state: str, **options):
        user = get_user_model().objects.filter(email=email).first()
        if user is None:
            raise CommandError(f"No existe la cuenta {email}.")
        if state == "on":
            shifts.start_shift(user, hours=12)
        else:
            shifts.end_shift(user)
        self.stdout.write(f"{email}: {'de turno' if state == 'on' else 'fuera de turno'}")
