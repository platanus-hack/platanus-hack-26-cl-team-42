"""Estado de cada paciente en la bandeja «Mis pacientes».

Resume, para el profesional, si un paciente necesita algo de él: un informe propio por
validar, un dictado que todavía se procesa o uno que falló. Solo cuentan los dictados e
informes del propio profesional; el último dictado considera a todo el equipo.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum
from uuid import UUID

from django.core.exceptions import ObjectDoesNotExist
from django.db.models import Max
from django.utils import timezone

from apps.recordings.models import Recording

from .models import ExtractedRecord, Report, Transcription


class InboxStatus(StrEnum):
    REVIEW = "review"
    FAILED = "failed"
    PROCESSING = "processing"
    UP_TO_DATE = "up_to_date"


@dataclass(frozen=True)
class InboxState:
    status: InboxStatus
    last_dictation_at: datetime | None
    # Dictado propio cuya transcripción falló y se puede reintentar.
    retry_recording_id: UUID | None = None
    # Mientras se procesa: en qué etapa va (1 a ``PROCESSING_STEPS``; 0 = en cola) y su nombre.
    stage_step: int | None = None
    stage_label: str | None = None


def inbox_states(professional, patient_ids: list[int]) -> dict[int, InboxState]:
    """El estado en la bandeja de cada paciente, para el profesional."""
    last_dictations = dict(
        Recording.objects.filter(patient_id__in=patient_ids)
        .values("patient_id")
        .annotate(last=Max("recorded_at"))
        .values_list("patient_id", "last")
    )
    reviewing = set(
        Report.objects.filter(
            author=professional, patient_id__in=patient_ids, status=Report.Status.REVIEW
        ).values_list("patient_id", flat=True)
    )
    own = _own_recordings(professional, patient_ids)
    states = {}
    for patient_id in patient_ids:
        recordings = own.get(patient_id, [])
        status, retry_id = _status(patient_id in reviewing, recordings)
        step, label = (
            _processing_detail(recordings) if status == InboxStatus.PROCESSING else (None, None)
        )
        states[patient_id] = InboxState(
            status, last_dictations.get(patient_id), retry_id, step, label
        )
    return states


IN_PROGRESS = {"pending", "processing"}
# Etapas visibles de un dictado en proceso: transcribir, parsear a la plantilla, homologar.
PROCESSING_STEPS = 3
# Si tras este plazo el paso siguiente no existe, el proceso quedó detenido (p. ej. no se
# reconoció la plantilla del dictado) y se informa como fallido.
STALLED_AFTER = timedelta(minutes=2)


def _own_recordings(professional, patient_ids: list[int]) -> dict[int, list[Recording]]:
    """Los dictados propios de cada paciente, del más reciente al más antiguo."""
    recordings = (
        Recording.objects.filter(professional=professional, patient_id__in=patient_ids)
        .select_related("transcription__extracted_record__report")
        .order_by("-recorded_at")
    )
    grouped: dict[int, list[Recording]] = {}
    for recording in recordings:
        grouped.setdefault(recording.patient_id, []).append(recording)
    return grouped


def _status(has_review: bool, recordings: list[Recording]) -> tuple[InboxStatus, UUID | None]:
    if has_review:
        return InboxStatus.REVIEW, None
    if recordings:
        latest_stage = _stage(recordings[0])
        if latest_stage == "failed":
            retryable = _transcription(recordings[0]).status == Transcription.Status.FAILED
            return InboxStatus.FAILED, recordings[0].id if retryable else None
    if any(_stage(recording) == "processing" for recording in recordings):
        return InboxStatus.PROCESSING, None
    return InboxStatus.UP_TO_DATE, None


def _processing_detail(recordings: list[Recording]) -> tuple[int | None, str | None]:
    """Etapa del dictado propio más reciente que todavía se procesa."""
    for recording in recordings:
        if _stage(recording) != "processing":
            continue
        transcription = _transcription(recording)
        if transcription is None or transcription.status == Transcription.Status.PENDING:
            return 0, "En cola"
        if transcription.status == Transcription.Status.PROCESSING:
            return 1, "Transcribiendo el audio"
        record = _related(transcription, "extracted_record")
        if record is None:
            return 2, "Identificando la plantilla"
        if record.status in IN_PROGRESS:
            return 2, "Parseando a la plantilla"
        return 3, "Homologando los conceptos"
    return None, None


def _stage(recording: Recording) -> str:
    """«processing», «failed» o «done»: en qué quedó el proceso del dictado."""
    transcription = _transcription(recording)
    if transcription is None or transcription.status in IN_PROGRESS:
        return "processing"
    if transcription.status == Transcription.Status.FAILED:
        return "failed"
    record = _related(transcription, "extracted_record")
    if record is None:
        return _waiting_since(transcription.updated_at)
    if record.status in IN_PROGRESS:
        return "processing"
    if record.status == ExtractedRecord.Status.FAILED:
        return "failed"
    report = _related(record, "report")
    if report is None:
        return _waiting_since(record.updated_at)
    if report.status == Report.Status.PROCESSING:
        return "processing"
    if report.status == Report.Status.FAILED:
        return "failed"
    return "done"


def _waiting_since(moment: datetime) -> str:
    return "failed" if timezone.now() - moment > STALLED_AFTER else "processing"


def _transcription(recording: Recording) -> Transcription | None:
    return _related(recording, "transcription")


def _related(obj, name: str):
    """El objeto relacionado uno a uno, o ``None`` si todavía no existe."""
    try:
        return getattr(obj, name)
    except ObjectDoesNotExist:
        return None
