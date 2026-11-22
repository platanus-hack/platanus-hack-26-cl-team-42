"""Reglas de negocio para crear y eliminar dictados."""

from __future__ import annotations

import re
import unicodedata
from datetime import datetime, timedelta

from django.core.files.uploadedfile import UploadedFile
from django.db import transaction
from django.utils import timezone

from apps.clinical_templates.models import ClinicalTemplate

from .models import Patient, Recording

MAX_REFERENCE_LENGTH = 120
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


PROFESSION_LABELS = {
    "medico": "Médico UCI",
    "especialista": "Especialista",
    "enfermeria": "Enfermería",
    "tens": "TENS",
    "kinesiologia": "Kinesiología",
    "nutricionista": "Nutrición",
}


class PatientError(ValueError):
    """No se pudo crear el paciente."""


class DuplicatePatientError(PatientError):
    """Ya existe un paciente con ese identificador."""


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
    patient: Patient | None = None,
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

    if patient is not None:
        if not patient.assigned_to.filter(pk=professional.pk).exists():
            raise RecordingError("El paciente no está asignado a tu cuenta.")
        patient_reference = patient.reference[:MAX_REFERENCE_LENGTH]

    recorded_at = recorded_at or timezone.now()
    if recorded_at > timezone.now() + timedelta(minutes=5):
        raise RecordingError("La hora de grabación está en el futuro.")
    # El tipo de profesional sale, en orden, de lo indicado, del nombre del archivo subido
    # y de la cuenta; si no hay ninguno, se deduce luego del contenido del dictado.
    profession = profession or profession_from_name(audio.name) or professional.profession

    recording = Recording(
        professional=professional,
        name=recording_name(professional, profession, recorded_at),
        patient=patient,
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


def profession_from_name(filename: str | None) -> str:
    """Tipo de profesional que nombra un archivo («Dr. Rojas - Médico UCI - 18-11-2026.wav»)."""
    plain = _plain(filename or "")
    for value, label in PROFESSION_LABELS.items():
        if re.search(rf"\b{re.escape(_plain(label))}\b", plain):
            return value
    return ""


def _plain(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text.lower())
    return "".join(char for char in decomposed if not unicodedata.combining(char))


def recording_name(professional, profession: str, recorded_at: datetime) -> str:
    """«Dra. Soto · Kinesiología · 21-11-2026 10:30»: cuenta, tipo de profesional y hora."""
    account = professional.name or professional.email
    parts = [
        account,
        PROFESSION_LABELS.get(profession, ""),
        timezone.localtime(recorded_at).strftime("%d-%m-%Y %H:%M"),
    ]
    return " · ".join(part for part in parts if part)


def delete_recording(recording: Recording) -> None:
    """Delete the row and its stored audio file."""
    storage, name = recording.audio.storage, recording.audio.name
    recording.delete()
    if name:
        transaction.on_commit(lambda: storage.delete(name))


def create_patient(professional, *, name: str, identifier: str = "", bed: str = "") -> Patient:
    """Crea un paciente y se lo asigna a quien lo registra.

    El identificador (RUT, ficha) es opcional, pero si viene no puede repetirse: un paciente
    que ya existe se pide por traspaso a quien lo tiene, no se duplica.
    """
    name, identifier, bed = name.strip(), identifier.strip(), bed.strip()
    if not name:
        raise PatientError("Indica el nombre del paciente.")
    if len(name) > Patient._meta.get_field("name").max_length:
        raise PatientError("El nombre es demasiado largo.")
    if len(identifier) > Patient._meta.get_field("identifier").max_length:
        raise PatientError("El identificador es demasiado largo.")
    if len(bed) > Patient._meta.get_field("bed").max_length:
        raise PatientError("La cama es demasiado larga.")
    with transaction.atomic():
        if identifier:
            existing = Patient.objects.select_for_update().filter(identifier__iexact=identifier)
            if existing.filter(assigned_to=professional).exists():
                raise DuplicatePatientError("Ya tienes asignado un paciente con ese identificador.")
            if existing.exists():
                raise DuplicatePatientError(
                    "Ya existe un paciente con ese identificador; pide que te lo traspasen."
                )
        patient = Patient.objects.create(name=name, identifier=identifier, bed=bed)
        patient.assigned_to.add(professional)
    return patient


def patients_of(professional):
    """Pacientes asignados al profesional."""
    return Patient.objects.filter(assigned_to=professional)
