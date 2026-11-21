"""Reglas de negocio para crear y eliminar dictados."""

from __future__ import annotations

from datetime import datetime, timedelta

from django.core.files.uploadedfile import UploadedFile
from django.db import transaction
from django.utils import timezone

from apps.clinical_templates.models import ClinicalTemplate

from .models import Recording

MAX_AUDIO_BYTES = 100 * 1024 * 1024  # ~1 h de opus/aac a calidad de voz
ALLOWED_MIME_TYPES = frozenset(
    {
        "audio/webm",  # Chrome / Firefox MediaRecorder
        "audio/ogg",
        "audio/mp4",  # Safari MediaRecorder
        "audio/x-m4a",
        "audio/m4a",
        "audio/aac",
        "audio/mpeg",
        "audio/wav",
        "audio/x-wav",
        "audio/wave",
        "video/webm",  # Algunos navegadores etiquetan el audio de MediaRecorder así
    }
)


class RecordingError(ValueError):
    """El audio recibido no puede guardarse como dictado."""


def base_mime_type(content_type: str | None) -> str:
    """``audio/webm;codecs=opus`` → ``audio/webm``."""
    return (content_type or "").split(";", 1)[0].strip().lower()


def create_recording(
    *,
    professional,
    audio: UploadedFile,
    source: str,
    recorded_at: datetime | None = None,
    duration_seconds: float | None = None,
    patient_reference: str = "",
    note: str = "",
    profession: str = "",
    specialty: str = "",
) -> Recording:
    mime_type = base_mime_type(audio.content_type)
    if mime_type not in ALLOWED_MIME_TYPES:
        raise RecordingError(f"Formato de audio no soportado: {mime_type or 'desconocido'}")
    if audio.size == 0:
        raise RecordingError("El audio está vacío.")
    if audio.size > MAX_AUDIO_BYTES:
        raise RecordingError("El audio supera el tamaño máximo permitido (100 MB).")
    if source not in Recording.Source.values:
        raise RecordingError(f"Origen inválido: {source}")
    if duration_seconds is not None and duration_seconds < 0:
        raise RecordingError("La duración no puede ser negativa.")

    if profession and profession not in ClinicalTemplate.Profession.values:
        raise RecordingError(f"Tipo de profesional inválido: {profession}")

    recorded_at = recorded_at or timezone.now()
    if recorded_at > timezone.now() + timedelta(minutes=5):
        raise RecordingError("La hora de grabación está en el futuro.")

    recording = Recording(
        professional=professional,
        patient_reference=patient_reference.strip(),
        note=note.strip(),
        profession=profession,
        specialty=specialty.strip(),
        mime_type=mime_type,
        size_bytes=audio.size,
        duration_seconds=duration_seconds,
        source=source,
        recorded_at=recorded_at,
    )
    with transaction.atomic():
        recording.audio.save(audio.name or "audio", audio, save=False)
        recording.save()
    return recording


def delete_recording(recording: Recording) -> None:
    """Delete the row and its stored audio file."""
    storage, name = recording.audio.storage, recording.audio.name
    recording.delete()
    if name:
        transaction.on_commit(lambda: storage.delete(name))
