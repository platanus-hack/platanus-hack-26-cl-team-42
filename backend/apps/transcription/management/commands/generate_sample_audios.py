"""Genera audios de ejemplo en español para cada tipo de profesional."""

import io
import wave
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

SAMPLES_DIR = Path(__file__).parent.parent.parent / "samples"

SAMPLE_TEXTS = {
    "medico_uci": """Paciente en box 7, día 3 de estadía UCI. Varón de 68 años con diagnóstico de sepsis
    de foco abdominal. Presión arterial media 72 mmHg, frecuencia cardíaca 95, saturación 94%.
    Recibe noradrenalina 0.1 microgramos por kilo por minuto. Lactato arterial 3.2.
    Cultivos pendientes. Se incrementó dosis de piperacilina tazobactam. Próximo control en 6 horas.""",

    "enfermeria_uci": """Paciente de box 7 presenta herida quirúrgica limpia sin signos de infección.
    Apósito seco. Se realizó cambio de posición a las 10 de la mañana. Diuresis adecuada,
    aproximadamente 40 mililitros por hora. Tolerancia a nutrición enteral, residuo gástrico menor
    a 100 mililitros. Catéter venoso central permeable sin signos de flebitis.""",

    "kinesiologia_uci": """Evaluación de paciente en box 7. Presenta limitación importante de movilidad
    en miembros inferiores. Se realizaron maniobras de movilización pasiva con rango completo.
    Se inició programa de ejercicios activo-asistidos. Paciente tolera bien la intervención.
    Se recomienda continuar con kinesia dos veces al día y cambios de posición cada dos horas.""",

    "tens_uci": """Monitoreo de paciente en cama 7. Signos vitales estables. Conexión de monitores
    funcionando correctamente. Se verificó permeabilidad de vías periféricas. Paciente recibió medicación
    según indicación médica a las 14 horas. Se mantiene en ayuno. Próxima evaluación a las 18 horas.""",

    "especialista_interconsulta": """Consulta interconsulta por cardiología. Paciente con antecedente
    de hipertensión e insuficiencia cardíaca. Se revisan resultados de electrocardiograma: sin cambios
    agudos. Se recomienda mantener tratamiento actual con furosemida y enalapril. Próximo ecocardiograma
    en control ambulatorio. Se sugiere derivación a programa de rehabilitación cardíaca.""",
}


class Command(BaseCommand):
    help = "Genera audios de ejemplo en español para testing"

    def add_arguments(self, parser):
        parser.add_argument(
            "--force",
            action="store_true",
            help="Sobrescribe audios existentes",
        )

    def handle(self, *args, **options):
        try:
            import pyttsx3
        except ImportError:
            raise CommandError(
                "pyttsx3 no está instalado. Ejecuta: uv pip install pyttsx3"
            )

        SAMPLES_DIR.mkdir(exist_ok=True)
        force = options["force"]

        for slug, text in SAMPLE_TEXTS.items():
            output_path = SAMPLES_DIR / f"{slug}.wav"
            if output_path.exists() and not force:
                self.stdout.write(f"⏭️  {slug} ya existe (usa --force para sobrescribir)")
                continue

            self.stdout.write(f"🎙️  Generando {slug}...", ending=" ")
            try:
                _generate_audio(text, str(output_path))
                self.stdout.write(self.style.SUCCESS("✓"))
            except Exception as error:
                raise CommandError(f"Error generando {slug}: {error}")

        self.stdout.write(
            self.style.SUCCESS(f"\n✅ Audios de ejemplo generados en {SAMPLES_DIR}")
        )


def _generate_audio(text: str, output_path: str) -> None:
    """Genera un archivo WAV en español usando pyttsx3."""
    import pyttsx3

    engine = pyttsx3.init()
    engine.setProperty("rate", 150)  # Velocidad de pronunciación

    # Intentar usar voz en español (es según el sistema operativo)
    voices = engine.getProperty("voices")
    spanish_voice = None
    for voice in voices:
        if "spanish" in voice.languages or "es" in voice.id.lower():
            spanish_voice = voice.id
            break

    if spanish_voice:
        engine.setProperty("voice", spanish_voice)

    # Guardar como WAV
    engine.save_to_file(text, output_path)
    engine.runAndWait()
    engine.stop()
