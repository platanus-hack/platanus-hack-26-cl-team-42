"""Informes: el registro extraído, con sus conceptos homologados y firmado por su autor.

Es el último paso automático del pipeline (audio -> transcripción -> parseo -> homologación ->
informe). Cada informe guarda quién lo generó y el número de orden dentro de su categoría
profesional para el paciente (primer informe de kinesiología, segundo…).
"""

import logging
from datetime import datetime
from typing import Any

from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from pydantic import BaseModel

from apps.clinical_templates import services as template_services

from . import (
    consolidation_services,
    evidence_services,
    homologation_services,
    report_topics,
    review_services,
)
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
    templateVersion: int
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
    # Temas del informe (agrupan sus secciones para leerlo completo) y sus notas sin categoría
    # (familia y observaciones).
    topics: list[report_topics.Topic]
    noteSections: list[str]
    # Puntos que el autor debe revisar antes de guardar (los más graves primero).
    reviewItems: list[review_services.ReviewItem]
    # Contradicciones con los exámenes del paciente (también entre los puntos a revisar).
    evidenceAlerts: list[dict[str, Any]]
    # Qué pasó al guardarse respecto de la versión oficial: official | merged | reconciling | …
    consolidation: str
    # Solo su autor puede completarlo y validarlo, y solo mientras está por validar.
    canEdit: bool
    editRevision: str
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

    Si se rehace porque se completó una sección, sus aclaraciones ya revisadas vuelven a quedar
    pendientes; las demás conservan su revisión (y las alertas de evidencia, la suya).
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
        report.validated_sections = review_services.reviewed_after_change(
            report.validated_sections, changed_section
        )
        report.evidence_alerts = _evidence_alerts(report)
        # Queda por validar: el autor revisa los puntos pendientes y lo guarda.
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


class ItemEditError(ValueError):
    """El cambio no corresponde a un ítem de la plantilla."""


@transaction.atomic
def edit_item(
    report: Report, section: str, index: int | None, value: Any, revision: str
) -> Report:
    """Aplica la corrección literal y sincroniza el registro del borrador."""
    _lock_reviewable_report(report)
    if report.updated_at.isoformat() != revision:
        raise ValidationError("El informe cambió. Vuelve a abrir el ítem para editarlo.")
    record = report.extracted_record
    data, extracted = report.data or {}, record.data or {}
    properties = record.template.output_schema["properties"]
    if section == "metadatos" or section not in properties or section not in data:
        raise ItemEditError("La sección no está disponible para editar.")

    shown, original = data[section], extracted.get(section)
    if isinstance(shown, list):
        if index is None or not 0 <= index < len(shown):
            raise ItemEditError("Selecciona un ítem de la sección.")
        if not isinstance(original, list) or len(original) != len(shown):
            raise ValidationError("El registro y el informe aún no están sincronizados.")
        _preserve_quotes(shown[index], value)
        edited, changed_paths = _manual_changes(
            original[index], shown[index], value, f"{section}[{index}]"
        )
        new_extracted, new_shown = original.copy(), shown.copy()
        new_extracted[index], new_shown[index] = edited, value
    elif index is None:
        _preserve_quotes(shown, value)
        new_extracted, changed_paths = _manual_changes(original, shown, value, section)
        new_shown = value
    else:
        raise ItemEditError("La sección no contiene ítems numerados.")

    if not changed_paths:
        return report
    _validate_item_edit(record, section, original, new_extracted)

    record.data = {**extracted, section: new_extracted}
    record.save(update_fields=["data", "updated_at"])
    report.data = {**data, section: new_shown}
    report.homologations = [
        item
        for item in report.homologations
        if not any(
            item["path"] == prefix or item["path"].startswith((f"{prefix}.", f"{prefix}["))
            for prefix in changed_paths
        )
    ]
    report.validated_sections = review_services.reviewed_after_change(
        report.validated_sections, section, index
    )
    report.evidence_alerts = evidence_services.check_report(report, edited_section=section)
    report.save(
        update_fields=[
            "data", "homologations", "validated_sections", "evidence_alerts", "updated_at"
        ]
    )
    return report


def _manual_changes(original: Any, shown: Any, value: Any, path: str) -> tuple[Any, set[str]]:
    """Copia los campos modificados, conservando los términos extraídos del resto."""
    if isinstance(shown, dict) and isinstance(value, dict):
        result = original.copy() if isinstance(original, dict) else {}
        changed = set()
        for key in shown.keys() | value.keys():
            key_path = f"{path}.{key}"
            if key not in value:
                result.pop(key, None)
                changed.add(key_path)
                continue
            updated, fields = _manual_changes(result.get(key), shown.get(key), value[key], key_path)
            if fields or key not in shown:
                result[key] = updated
                changed.update(fields or {key_path})
        return result, changed
    if isinstance(shown, list) and isinstance(value, list):
        items = []
        changed = {f"{path}[{index}]" for index in range(len(value), len(shown))}
        for index, after in enumerate(value):
            item_path = f"{path}[{index}]"
            if index >= len(shown):
                items.append(after)
                changed.add(item_path)
                continue
            before = shown[index]
            raw = (
                original[index] if isinstance(original, list) and index < len(original) else before
            )
            updated, fields = _manual_changes(raw, before, after, item_path)
            items.append(updated)
            changed.update(fields)
        return items, changed
    if type(shown) is type(value) and shown == value:
        return original, set()
    return value, {path}


def _preserve_quotes(before: Any, after: Any) -> None:
    def quotes(node: Any, path: tuple = ()) -> dict:
        found = {}
        if isinstance(node, dict):
            for key, value in node.items():
                if key == "evidencia" and value is not None:
                    found[path] = value
                else:
                    found.update(quotes(value, (*path, key)))
        elif isinstance(node, list):
            for index, value in enumerate(node):
                found.update(quotes(value, (*path, index)))
        return found

    if quotes(before) != quotes(after):
        raise ItemEditError("Las citas de la transcripción se conservan.")


def _validate_item_edit(record: ExtractedRecord, section: str, original: Any, value: Any) -> None:
    # Los registros históricos pueden tener otros campos incompletos en la sección.
    issues = template_services.validate_section(record.template, section, {section: value})
    if not issues:
        return
    previous = {
        (issue.path, issue.message)
        for issue in template_services.validate_section(
            record.template, section, {section: original}
        )
    }
    for issue in issues:
        if (issue.path, issue.message) not in previous:
            raise ItemEditError(f"Revisa el campo {issue.path}: {issue.message}")


def topics_of(report: Report) -> list[report_topics.Topic]:
    return report_topics.group_sections(list(report.data or {}))


@transaction.atomic
def review_item(report: Report, item_id: str) -> Report:
    """El autor da por revisado un punto pendiente (alerta de evidencia o aclaración)."""
    _lock_reviewable_report(report)
    try:
        review_services.mark_reviewed(report, item_id)
    except review_services.ReviewError as error:
        raise ValidationError(str(error)) from error
    return report


def pending_review_items(report: Report) -> list[review_services.ReviewItem]:
    """Los puntos que el autor aún debe revisar; sin ninguno, puede guardar el informe."""
    return review_services.pending_items(report)


@transaction.atomic
def validate_report(report: Report) -> Report:
    """Guarda el informe: sin puntos pendientes pasa a *guardado* (``done``) y se cierra."""
    _lock_reviewable_report(report)
    missing = pending_review_items(report)
    if missing:
        count = len(missing)
        raise ValidationError(
            f"Falta revisar {count} {'punto' if count == 1 else 'puntos'} "
            "antes de guardar el informe."
        )
    report.status = Report.Status.DONE
    report.validated_at = timezone.now()
    report.save(update_fields=["status", "validated_at", "updated_at"])
    # Ya guardado: se compara con la versión oficial del paciente (o pasa a serlo).
    return consolidation_services.consolidate(report)


def _lock_reviewable_report(report: Report) -> None:
    report.refresh_from_db(from_queryset=Report.objects.select_for_update())
    if report.status != Report.Status.REVIEW:
        raise ValidationError("El informe debe estar por validar.")
    if report.extracted_record.status != ExtractedRecord.Status.DONE:
        raise ValidationError("Espera a que termine de actualizarse el informe.")


def acknowledge_alert(report: Report, alert_id: str) -> Report:
    """El autor da por revisada una alerta de evidencia (queda marcada, no se borra)."""
    if report.status != Report.Status.REVIEW:
        raise ValidationError("Solo se revisan las alertas de un informe por validar.")
    if alert_id not in {alert["id"] for alert in report.evidence_alerts}:
        raise ValidationError("No existe esa alerta.")
    return review_item(report, alert_id)


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
        templateVersion=record.template.version,
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
        evidenceAlerts=review_services.report_evidence_alerts(report),
        consolidation=report.consolidation,
        validatedAt=report.validated_at,
        topics=topics_of(report),
        noteSections=report_topics.note_sections(list(report.data or {})),
        reviewItems=review_services.review_items(report) if report.data else [],
        canEdit=(
            viewer is not None
            and report.author_id == viewer.id
            and report.status == Report.Status.REVIEW
        ),
        editRevision=report.updated_at.isoformat(),
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
