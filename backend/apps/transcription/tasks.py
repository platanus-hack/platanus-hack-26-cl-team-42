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
