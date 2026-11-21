from django.core.management.base import BaseCommand

from apps.transcription.services import load_sample_audio


class Command(BaseCommand):
    help = "Carga el audio de ejemplo en la base de datos y lo transcribe automáticamente."

    def handle(self, *args, **options):
        transcription = load_sample_audio()
        self.stdout.write(f"{transcription.name}: {transcription.text}")
