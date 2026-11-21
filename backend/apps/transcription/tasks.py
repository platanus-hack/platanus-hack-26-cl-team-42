"""Tareas de Celery del módulo de transcripción."""

from conf.celery import app

from . import services


@app.task(name="transcription.tasks.transcribe_recording")
def transcribe_recording(transcription_id: int) -> str:
    """Transcribe el audio de un dictado con Whisper y guarda el texto."""
    return services.run_transcription(transcription_id)
