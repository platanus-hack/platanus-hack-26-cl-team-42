from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

from apps.transcription.services import load_sample_audio


class Command(BaseCommand):
    help = "Crea un dictado con el audio de ejemplo para un usuario y lo transcribe al instante."

    def add_arguments(self, parser):
        parser.add_argument("email", help="Correo del profesional dueño del dictado de ejemplo.")

    def handle(self, *args, email: str, **options):
        try:
            professional = get_user_model().objects.get(email=email)
        except get_user_model().DoesNotExist as error:
            raise CommandError(f"No existe un usuario con el correo {email}") from error
        transcription = load_sample_audio(professional)
        self.stdout.write(f"{transcription.name} [{transcription.status}]: {transcription.text}")
