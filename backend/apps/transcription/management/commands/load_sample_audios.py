"""Carga audios de ejemplo y los procesa para testing."""

from pathlib import Path

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from apps.recordings.models import Recording
from apps.recordings.services import create_recording

from ...extraction_services import request_extraction
from ...services import request_transcription

SAMPLES_DIR = Path(__file__).parent.parent.parent / "samples"

User = get_user_model()

# Mapeo: profesional_type → (sample_filename, template_slug)
PROFESSIONAL_SAMPLES = {
    "medico": ("medico_uci.wav", "medico_uci"),
    "enfermeria": ("enfermeria_uci.wav", "enfermeria_uci"),
    "kinesiologia": ("kinesiologia_uci.wav", "kinesiologia_uci"),
    "tens": ("tens_uci.wav", "tens_uci"),
    "especialista": ("especialista_interconsulta.wav", "especialista_interconsulta"),
}


class Command(BaseCommand):
    help = "Carga audios de ejemplo para testing y extrae información"

    def add_arguments(self, parser):
        parser.add_argument(
            "--professional-email",
            type=str,
            help="Email del profesional para cargar muestras (admin@example.com si no existe)",
        )
        parser.add_argument(
            "--wait-extraction",
            action="store_true",
            help="Espera a que terminen transcripciones y extracción",
        )

    def handle(self, *args, **options):
        email = options.get("professional_email") or "admin@example.com"
        wait = options.get("wait_extraction", False)

        try:
            user = User.objects.get(email=email)
        except User.DoesNotExist:
            # Crear admin si no existe
            user = User.objects.create_superuser(email=email, password="admin123")
            self.stdout.write(f"✨ Creado usuario: {email}")

        self.stdout.write(f"\n📂 Buscando audios en: {SAMPLES_DIR}")
        if not SAMPLES_DIR.exists():
            raise CommandError(f"Carpeta de muestras no existe: {SAMPLES_DIR}")

        for prof_type, (filename, template_slug) in PROFESSIONAL_SAMPLES.items():
            audio_path = SAMPLES_DIR / filename
            if not audio_path.exists():
                self.stdout.write(
                    self.style.WARNING(f"⏭️  {prof_type}: {filename} no encontrado")
                )
                continue

            self.stdout.write(f"\n🎙️  Cargando {prof_type}...", ending=" ")

            try:
                # Crear grabación
                audio_file = SimpleUploadedFile(
                    filename,
                    audio_path.read_bytes(),
                    content_type="audio/wav",
                )
                recording = create_recording(
                    professional=user,
                    audio=audio_file,
                    source=Recording.Source.UPLOAD,
                    recorded_at=timezone.now(),
                    patient_reference=f"Ejemplo {prof_type} - Box 7",
                    note=f"Grabación de ejemplo para testing ({prof_type})",
                )
                self.stdout.write(self.style.SUCCESS("✓"))

                # Transcribir
                self.stdout.write(f"📝 Transcribiendo {prof_type}...", ending=" ")
                request_transcription(recording)
                self.stdout.write(self.style.SUCCESS("✓ (en cola)"))

                # Extraer información
                self.stdout.write(f"🔍 Extrayendo información {prof_type}...", ending=" ")
                request_extraction(recording, template_slug)
                self.stdout.write(self.style.SUCCESS("✓ (en cola)"))

            except Exception as error:
                raise CommandError(f"Error cargando {prof_type}: {error}")

        self.stdout.write(
            self.style.SUCCESS("\n✅ Audios de ejemplo cargados en cola de Celery")
        )
        if wait:
            self.stdout.write("⏳ Esperando a que se procesen... (Ctrl+C para cancelar)")
            self._wait_for_processing(user)

    def _wait_for_processing(self, user):
        import time

        from ...models import ExtractedRecord, Transcription

        # Esperar a que terminen todas las tareas
        for _ in range(300):  # 5 minutos máximo
            pending = Transcription.objects.filter(
                recording__professional=user, status=Transcription.Status.PENDING
            ).count()
            processing_trans = Transcription.objects.filter(
                recording__professional=user, status=Transcription.Status.PROCESSING
            ).count()
            processing_extract = ExtractedRecord.objects.filter(
                transcription__recording__professional=user,
                status=ExtractedRecord.Status.PROCESSING,
            ).count()

            if pending == 0 and processing_trans == 0 and processing_extract == 0:
                break

            self.stdout.write(
                f"  Pendientes: {pending}, Procesando trans: {processing_trans}, "
                f"Procesando extract: {processing_extract}"
            )
            time.sleep(2)

        # Mostrar resultados
        transcriptions = Transcription.objects.filter(
            recording__professional=user
        ).select_related("recording", "extracted_record")

        for trans in transcriptions:
            status_icon = (
                "✓" if trans.status == Transcription.Status.DONE else "✗"
            )
            self.stdout.write(f"{status_icon} {trans.recording.patient_reference}: {trans.status}")
            if trans.extracted_record:
                extract_icon = (
                    "✓" if trans.extracted_record.status == ExtractedRecord.Status.DONE else "✗"
                )
                self.stdout.write(
                    f"  {extract_icon} Extracción: {trans.extracted_record.status}"
                )
