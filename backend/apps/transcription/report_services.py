"""Informes: el registro extraído, con sus conceptos homologados y firmado por su autor.

Es el último paso automático del pipeline (audio -> transcripción -> parseo -> homologación ->
informe). Cada informe guarda quién lo generó y el número de orden dentro de su categoría
profesional para el paciente (primer informe de kinesiología, segundo…).
"""

import logging
from datetime import datetime
from typing import Any

from django.db.models import Q
from django.utils import timezone
from pydantic import BaseModel

from . import consolidation_services, evidence_services, homologation_services, report_topics
from .extraction_services import ExtractionOut
from .extraction_services import to_out as extraction_to_out
from .models import ExtractedRecord, Report, Transcription
from .services import TranscriptionOut
from .services import to_out as transcription_to_out

logger = logging.getLogger(__name__)


class PatientRef(BaseModel):
    id: int
    name: str
    identifier: str
    bed: str


class ReportOut(BaseModel):
    id: str
    extractionId: str
    recordingId: str
    templateSlug: str
    templateName: str
    status: str
    profession: str
    patientReference: str
    patient: PatientRef | None
    authorName: str
    authorEmail: str
    # 1 = primer informe de esa categoría profesional para el paciente, 2 = segundo…
    sequence: int
    data: dict[str, Any] | None
    homologations: list[dict[str, Any]]
    error: str
    # Estado del parseo del registro: «processing» mientras se incorpora información nueva.
    extractionStatus: str
    validatedAt: datetime | None
    # Temas del informe (agrupan sus secciones) y cuáles validó ya el autor.
    topics: list[report_topics.Topic]
    validatedTopics: list[str]
    # Contradicciones con los exámenes del paciente, para revisarlas al validar.
    evidenceAlerts: list[dict[str, Any]]
    # Qué pasó al guardarse respecto de la versión oficial: official | merged | reconciling | …
    consolidation: str
    # Solo su autor puede completarlo y validarlo, y solo mientras está por validar.
    canEdit: bool
    recordedAt: datetime
    created_at: datetime
    updated_at: datetime


class PipelineOut(BaseModel):
    """Estado de todas las etapas de un dictado, para seguirlas en una sola consulta."""

    recordingId: str
    transcription: TranscriptionOut | None
    extraction: ExtractionOut | None
    report: ReportOut | None


def generate_report(record: ExtractedRecord, changed_section: str | None = None) -> Report:
    """Homologa el registro extraído y lo guarda como informe (lo llama el worker).

    Si se rehace porque se completó una sección, el tema al que pertenece vuelve a quedar sin
    validar; los demás temas ya validados conservan su validación.
    """
    report = _start_report(record)

    def save_progress(entries: list[dict[str, Any]]) -> None:
        report.homologations = entries
        report.save(update_fields=["homologations", "updated_at"])

    try:
        result = homologation_services.homologate(
            record.data or {}, report.profession, save_progress
        )
    except Exception as error:
        logger.exception("Falló la homologación del registro %s", record.id)
        report.status = Report.Status.FAILED
        report.error = f"No se pudo homologar el registro: {error}"[:500]
    else:
        report.data = result.data
        report.homologations = result.entries
        topics = report_topics.group_sections(list(result.data))
        changed_topic = next((t.id for t in topics if changed_section in t.sections), None)
        report.validated_sections = [
            topic.id
            for topic in topics
            if topic.id in report.validated_sections and topic.id != changed_topic
        ]
        report.evidence_alerts = _evidence_alerts(report)
        # Queda por validar: el autor revisa lo que falta y lo acepta antes de darlo por generado.
        report.status = Report.Status.REVIEW
        report.validated_at = None
        report.error = ""
    report.save(
        update_fields=[
            "status",
            "data",
            "homologations",
            "validated_sections",
            "evidence_alerts",
            "error",
            "validated_at",
            "updated_at",
        ]
    )
    return report


def _evidence_alerts(report: Report) -> list[dict[str, Any]]:
    """Contradicciones con los exámenes; un fallo aquí nunca impide generar el informe."""
    try:
        return evidence_services.check_report(report)
    except Exception:
        logger.exception("No se pudo revisar la evidencia del informe %s", report.id)
        return report.evidence_alerts


class ValidationError(ValueError):
    """El informe o el tema no se pueden validar en su estado actual."""


def topics_of(report: Report) -> list[report_topics.Topic]:
    return report_topics.group_sections(list(report.data or {}))


def set_topic_validated(report: Report, topic_id: str, validated: bool) -> Report:
    """Marca (o desmarca) un tema del informe como validado por su autor."""
    if report.status != Report.Status.REVIEW:
        raise ValidationError("Solo se pueden validar los temas de un informe por validar.")
    if topic_id not in {topic.id for topic in topics_of(report)}:
        raise ValidationError(f"El informe no tiene el tema «{topic_id}».")
    current = [key for key in report.validated_sections if key != topic_id]
    report.validated_sections = [*current, topic_id] if validated else current
    report.save(update_fields=["validated_sections", "updated_at"])
    return report


def unvalidated_topics(report: Report) -> list[report_topics.Topic]:
    return [topic for topic in topics_of(report) if topic.id not in report.validated_sections]


def validate_report(report: Report) -> Report:
    """Guarda el informe: con todos los temas validados pasa a *guardado* (``done``) y se cierra."""
    if report.status != Report.Status.REVIEW:
        raise ValidationError("Solo se puede guardar un informe que está por validar.")
    missing = unvalidated_topics(report)
    if missing:
        names = ", ".join(topic.label for topic in missing)
        raise ValidationError(f"Faltan temas por validar antes de guardar el informe: {names}.")
    report.status = Report.Status.DONE
    report.validated_at = timezone.now()
    report.save(update_fields=["status", "validated_at", "updated_at"])
    # Ya guardado: se compara con la versión oficial del paciente (o pasa a serlo).
    return consolidation_services.consolidate(report)


def acknowledge_alert(report: Report, alert_id: str) -> Report:
    """El autor da por revisada una alerta de evidencia (queda marcada, no se borra)."""
    if report.status != Report.Status.REVIEW:
        raise ValidationError("Solo se revisan las alertas de un informe por validar.")
    found = False
    for alert in report.evidence_alerts:
        if alert["id"] == alert_id:
            alert["acknowledged"] = True
            found = True
    if not found:
        raise ValidationError("No existe esa alerta.")
    report.save(update_fields=["evidence_alerts", "updated_at"])
    return report


def reset_report(record: ExtractedRecord) -> None:
    """Deja el informe del registro en curso mientras éste se vuelve a generar."""
    Report.objects.filter(extracted_record=record).update(
        status=Report.Status.PROCESSING,
        data=None,
        homologations=[],
        validated_sections=[],
        error="",
    )


def list_reports(
    professional, patient_id: int | None = None, include_drafts: bool = False
) -> list[ReportOut]:
    """Informes guardados de los pacientes del profesional.

    Los borradores no son informes todavía: solo se incluyen, y solo los propios, si se pide
    (la bandeja los necesita para ofrecer «Informe por validar»).
    """
    condition = _saved(professional)
    if include_drafts:
        condition |= Q(author=professional) & ~Q(status=Report.Status.DONE)
    reports = _reports().filter(condition).distinct()
    if patient_id is not None:
        reports = reports.filter(patient_id=patient_id)
    return [to_out(report, professional) for report in reports]


def get_report(professional, report_id: int) -> ReportOut | None:
    """Un informe: los guardados del equipo del paciente y los borradores propios."""
    report = visible_reports(professional).filter(pk=report_id).first()
    return to_out(report, professional) if report else None


def saved_reports(professional):
    """Informes guardados (validados) de los pacientes asignados al profesional, o propios."""
    return _reports().filter(_saved(professional)).distinct()


def _saved(professional) -> Q:
    return Q(status=Report.Status.DONE) & (
        Q(patient__assigned_to=professional) | Q(author=professional)
    )


def visible_reports(professional):
    """Los guardados de sus pacientes y los propios en cualquier estado (borradores incluidos)."""
    validated_of_patients = Q(patient__assigned_to=professional, status=Report.Status.DONE)
    return _reports().filter(validated_of_patients | Q(author=professional)).distinct()


def get_pipeline(recording_id, professional) -> PipelineOut:
    transcription = (
        Transcription.objects.select_related("recording__professional")
        .filter(recording_id=recording_id, recording__professional=professional)
        .first()
    )
    record = (
        ExtractedRecord.objects.select_related("template", "transcription__recording")
        .filter(transcription=transcription)
        .first()
        if transcription
        else None
    )
    report = _reports().filter(extracted_record=record).first() if record else None
    return PipelineOut(
        recordingId=str(recording_id),
        transcription=transcription_to_out(transcription) if transcription else None,
        extraction=extraction_to_out(record) if record else None,
        report=to_out(report, professional) if report else None,
    )


def to_out(report: Report, viewer=None) -> ReportOut:
    record = report.extracted_record
    patient = report.patient
    return ReportOut(
        id=str(report.id),
        extractionId=str(record.id),
        recordingId=str(record.transcription.recording_id),
        templateSlug=record.template.slug,
        templateName=record.template.name,
        status=report.status,
        profession=report.profession,
        patientReference=report.patient_reference,
        patient=(
            PatientRef(
                id=patient.id, name=patient.name, identifier=patient.identifier, bed=patient.bed
            )
            if patient
            else None
        ),
        authorName=report.author.name or report.author.email,
        authorEmail=report.author.email,
        sequence=report.sequence,
        data=report.data,
        homologations=report.homologations,
        error=report.error,
        extractionStatus=record.status,
        evidenceAlerts=report.evidence_alerts,
        consolidation=report.consolidation,
        validatedAt=report.validated_at,
        topics=topics_of(report),
        validatedTopics=report.validated_sections,
        canEdit=(
            viewer is not None
            and report.author_id == viewer.id
            and report.status == Report.Status.REVIEW
        ),
        recordedAt=record.transcription.recording.recorded_at,
        created_at=report.created_at,
        updated_at=report.updated_at,
    )


def _reports():
    return Report.objects.select_related(
        "author",
        "patient",
        "extracted_record__template",
        "extracted_record__transcription__recording",
    )


def _start_report(record: ExtractedRecord) -> Report:
    """El informe del registro, en curso; conserva su número si paciente y categoría no cambian.

    Un informe que ya existía mantiene sus datos anteriores hasta que termina la nueva
    homologación, para que quien lo lee no lo vea vacío mientras se completa.
    """
    recording = record.transcription.recording
    profession = record.template.profession
    patient, reference = recording.patient, recording.patient_reference
    report = Report.objects.filter(extracted_record=record).first()
    same_group = report and (report.profession, report.patient_id, report.patient_reference) == (
        profession,
        recording.patient_id,
        reference,
    )
    if report and same_group:
        report.status, report.error = Report.Status.PROCESSING, ""
        report.save()
        return report

    # Los demás informes de la misma categoría para el paciente, de cualquier autor.
    others = Report.objects.filter(profession=profession)
    others = (
        others.filter(patient=patient) if patient else others.filter(patient_reference=reference)
    )
    if report:
        others = others.exclude(pk=report.pk)
    fields = {
        "author": recording.professional,
        "patient": patient,
        "profession": profession,
        "patient_reference": reference,
        "sequence": others.count() + 1,
        "status": Report.Status.PROCESSING,
        "data": None,
        "homologations": [],
        "validated_sections": [],
        "error": "",
    }
    if report:
        for name, value in fields.items():
            setattr(report, name, value)
        report.save()
        return report
    return Report.objects.create(extracted_record=record, **fields)
