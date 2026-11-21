"""Simula la carga de pacientes desde el otro sistema: crea ficticios y los asigna a un equipo.

    manage.py load_demo_patients [email]                          # por defecto test@localhost
    manage.py load_demo_patients [email] --colleague colega@localhost

Con ``--colleague`` los pacientes se reparten: la primera mitad queda con ``email`` y la
segunda con el colega (cuya cuenta se crea si no existe), para mostrar que cada profesional
solo ve a sus pacientes asignados.

Además crea el equipo demo (medico@, enfermeria@, kinesiologia@ y el externo especialista@,
todos con clave «test»), los pone de turno y les asigna los pacientes; el externo no recibe
ninguno. Es idempotente: los pacientes se identifican por su RUT ficticio y el reparto con el
colega se hace solo al crear su cuenta, así que no deshace traspasos posteriores.
"""

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

from apps.recordings.models import Patient
from apps.users import shifts

DEMO_PATIENTS = [
    {"name": "Juan Pérez Soto", "identifier": "11.111.111-1", "bed": "Box 7"},
    {"name": "María González Ruiz", "identifier": "12.222.222-2", "bed": "Box 3"},
    {"name": "Carlos Muñoz Araya", "identifier": "13.333.333-3", "bed": "Box 1"},
    {"name": "Ana Torres Vidal", "identifier": "14.444.444-4", "bed": "Box 5"},
    {"name": "Luis Fuentes Rojas", "identifier": "15.555.555-5", "bed": "Box 9"},
    {"name": "Rosa Herrera Díaz", "identifier": "16.666.666-6", "bed": "Box 2"},
]


# Equipo demo (clave «test»): permite ver los conflictos entre informes desde ambos lados.
DEMO_PROFESSIONALS = [
    {"email": "medico@localhost", "name": "Dr. Rojas", "profession": "medico"},
    {"email": "enfermeria@localhost", "name": "EU Soto", "profession": "enfermeria"},
    {"email": "kinesiologia@localhost", "name": "Klgo. Muñoz", "profession": "kinesiologia"},
    # Profesional externo: de turno para dar opiniones, pero sin pacientes asignados.
    {
        "email": "especialista@localhost",
        "name": "Dra. Fuentes",
        "profession": "especialista",
        "assigned": False,
    },
]
DEMO_PASSWORD = "test"
DEMO_SHIFT_HOURS = 12


class Command(BaseCommand):
    help = (
        "Asigna pacientes ficticios a una cuenta (o los reparte con un colega) y deja un equipo "
        "demo de profesionales, de turno, para probar conflictos entre informes."
    )

    def add_arguments(self, parser):
        parser.add_argument("email", nargs="?", default="test@localhost")
        parser.add_argument(
            "--colleague", help="Cuenta que recibe la segunda mitad de los pacientes."
        )
        parser.add_argument("--colleague-password", default="test")

    def handle(self, *args, email: str, colleague: str | None, colleague_password: str, **options):
        users = get_user_model()
        user = users.objects.filter(email=email).first()
        if user is None:
            raise CommandError(f"No existe la cuenta {email}.")
        patients = [
            Patient.objects.get_or_create(identifier=data["identifier"], defaults=data)[0]
            for data in DEMO_PATIENTS
        ]
        self._seed_team(patients, user)
        if colleague is None:
            self._assign(patients, user)
            return
        half = len(patients) // 2
        self._assign(patients[:half], user)
        if users.objects.filter(email=colleague).exists():
            return
        colleague_user = users.objects.create_user(
            email=colleague, password=colleague_password, name="Colega Demo"
        )
        self._hand_over(patients[half:], user, colleague_user)

    def _assign(self, patients: list[Patient], user) -> None:
        for patient in patients:
            patient.assigned_to.add(user)
            self.stdout.write(f"{patient.reference}: asignado a {user.email}")

    def _hand_over(self, patients: list[Patient], user, colleague) -> None:
        """Deja los pacientes con el colega (y ya no con ``user``)."""
        for patient in patients:
            patient.assigned_to.remove(user)
            patient.assigned_to.add(colleague)
            self.stdout.write(f"{patient.reference}: asignado a {colleague.email}")

    def _seed_team(self, patients: list[Patient], user) -> None:
        """Equipo demo: una cuenta por profesión, de turno y con los pacientes (el externo, no)."""
        users = get_user_model()
        team, external = [], []
        for data in DEMO_PROFESSIONALS:
            member, created = users.objects.get_or_create(
                email=data["email"],
                defaults={"name": data["name"], "profession": data["profession"]},
            )
            if created:
                member.set_password(DEMO_PASSWORD)
                member.save()
                self.stdout.write(f"Cuenta demo creada: {member.email} (clave {DEMO_PASSWORD})")
            (team if data.get("assigned", True) else external).append(member)
        for member in [user, *team, *external]:
            # La app conoce los turnos: el equipo demo queda de turno (si no lo estaba ya).
            if not shifts.is_on_shift(member):
                shifts.start_shift(member, hours=DEMO_SHIFT_HOURS)
        for patient in patients:
            patient.assigned_to.add(*team)
            patient.assigned_to.remove(*external)
