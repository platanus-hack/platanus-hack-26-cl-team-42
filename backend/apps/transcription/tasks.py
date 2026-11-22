"""Tareas de Celery del módulo de transcripción."""

from conf.celery import app

from . import extraction_services, services


@app.task(name="transcription.tasks.transcribe_recording")
def transcribe_recording(transcription_id: int) -> str:
    """Transcribe el audio de un dictado con Whisper y guarda el texto."""
    return services.run_transcription(transcription_id)


@app.task(name="transcription.tasks.extract_record_information")
def extract_record_information(record_id: int) -> str:
    """Extrae información estructurada de una transcripción con Qwen."""
    return extraction_services.run_extraction(record_id)


@app.task(name="transcription.tasks.update_record_section")
def update_record_section(record_id: int, section: str, text: str, audio_name: str) -> str:
    """Incorpora información nueva (texto y/o audio) a una sección del registro."""
    return extraction_services.run_section_update(record_id, section, text, audio_name)


@app.task(name="transcription.tasks.refine_conflict_guidance")
def refine_conflict_guidance(reconciliation_id: int) -> int:
    """Afina con el modelo la orientación de los conflictos de una reconciliación."""
    from .models import Conflict
    from .reconciliation_services import refine_guidance

    conflicts = Conflict.objects.filter(reconciliation_id=reconciliation_id)
    for conflict in conflicts:
        refine_guidance(conflict.id)
    return conflicts.count()


@app.task(name="transcription.tasks.run_panel", soft_time_limit=240, time_limit=300)
def run_panel(panel_id: int) -> None:
    """Corre la discusión multiagente de una consulta al panel y deja la recomendación."""
    from .panel_services import run_panel as run

    run(panel_id)


@app.task(soft_time_limit=45, time_limit=60)
def generate_patient_synthesis(
    stage: str, key: str, version_id: int, professional_id: int | None
) -> None:
    from .summary_services import generate_synthesis

    generate_synthesis(stage, key, version_id, professional_id)
