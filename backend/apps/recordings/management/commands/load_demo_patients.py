"""Simula la carga de pacientes desde el otro sistema: crea ficticios y los asigna a una cuenta.

    manage.py load_demo_patients [email]      # por defecto test@localhost

Es idempotente: los pacientes se identifican por su RUT ficticio.
"""

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

from apps.recordings.models import Patient

DEMO_PATIENTS = [
    {"name": "Juan Pérez Soto", "identifier": "11.111.111-1", "bed": "Box 7"},
    {"name": "María González Ruiz", "identifier": "12.222.222-2", "bed": "Box 3"},
    {"name": "Carlos Muñoz Araya", "identifier": "13.333.333-3", "bed": "Box 1"},
    {"name": "Ana Torres Vidal", "identifier": "14.444.444-4", "bed": "Box 5"},
    {"name": "Luis Fuentes Rojas", "identifier": "15.555.555-5", "bed": "Box 9"},
    {"name": "Rosa Herrera Díaz", "identifier": "16.666.666-6", "bed": "Box 2"},
]


class Command(BaseCommand):
    help = "Asigna pacientes ficticios a una cuenta (por defecto test@localhost)."

    def add_arguments(self, parser):
        parser.add_argument("email", nargs="?", default="test@localhost")

    def handle(self, *args, email: str, **options):
        user = get_user_model().objects.filter(email=email).first()
        if user is None:
            raise CommandError(f"No existe la cuenta {email}.")
        for data in DEMO_PATIENTS:
            patient, _ = Patient.objects.get_or_create(identifier=data["identifier"], defaults=data)
            patient.assigned_to.add(user)
            self.stdout.write(f"{patient.reference}: asignado a {email}")
