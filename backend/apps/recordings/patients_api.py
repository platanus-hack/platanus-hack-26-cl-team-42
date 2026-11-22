"""API de pacientes, montada en ``/-/api/patients``.

Cada profesional ve los pacientes que tiene asignados. Los pacientes vienen de otro sistema:
aquí no se crean, solo se listan y se traspasan a otro usuario.
"""

from datetime import datetime
from uuid import UUID

from django.contrib.auth import get_user_model
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404
from ninja import Router, Schema
from ninja.errors import HttpError

from apps.transcription import evidence_services
from apps.transcription.episode_services import pending_chart_counts
from apps.transcription.inbox_services import inbox_states
from apps.transcription.models import ConsolidatedVersion
from apps.transcription.reconciliation_services import open_conflict_counts
from apps.transcription.summary_services import (
    PatientOverview,
    PatientSummary,
    patient_overview,
    patient_summary,
)
from apps.transcription.trends_services import Trend, patient_trends
from apps.transcription.triage_services import triage_for

from . import services
from .api import PatientOut

router = Router(tags=["patients"])


class TransferIn(Schema):
    to_email: str


class PatientListOut(PatientOut):
    reportCount: int
    # Qué necesita el paciente del profesional: review, failed, processing o up_to_date.
    inboxStatus: str
    lastDictationAt: datetime | None
    retryRecordingId: UUID | None
    # Triage según la versión oficial: criticidad, prioridad de visita y tareas pendientes.
    criticality: str
    criticalityLabel: str
    pendingTasks: int
    visitPriority: str
    visitPriorityLabel: str
    priorityScore: float
    # Mientras se procesa un dictado propio: etapa (0 = en cola, 1 a 3) y su nombre.
    processingStep: int | None
    processingLabel: str | None
    # Conflictos abiertos entre informes de este paciente y cuántos son tuyos.
    openConflicts: int
    myOpenConflicts: int
    # Informes tuyos guardados que aún no pasas a la ficha institucional.
    pendingChart: int


@router.get("", response=list[PatientListOut])
def list_patients(request):
    """Pacientes asignados al profesional, con su número de informes y su estado en la bandeja."""
    patients = list(
        services.patients_of(request.user).annotate(
            report_count=Count("reports", filter=Q(reports__status="done"), distinct=True)
        )
    )
    ids = [p.id for p in patients]
    states = inbox_states(request.user, ids)
    conflicts = open_conflict_counts(request.user, ids)
    charting = pending_chart_counts(request.user, ids)
    triage = triage_for(ids, {pid: state.last_dictation_at for pid, state in states.items()})
    return [
        PatientListOut(
            id=p.id,
            name=p.name,
            identifier=p.identifier,
            bed=p.bed,
            reference=p.reference,
            reportCount=p.report_count,
            inboxStatus=states[p.id].status,
            lastDictationAt=states[p.id].last_dictation_at,
            retryRecordingId=states[p.id].retry_recording_id,
            criticality=triage[p.id].criticality,
            criticalityLabel=triage[p.id].criticality_label,
            pendingTasks=triage[p.id].pending_tasks,
            visitPriority=triage[p.id].visit_priority,
            visitPriorityLabel=triage[p.id].visit_priority_label,
            priorityScore=triage[p.id].priority_score,
            processingStep=states[p.id].stage_step,
            processingLabel=states[p.id].stage_label,
            openConflicts=conflicts[p.id][0],
            myOpenConflicts=conflicts[p.id][1],
            pendingChart=charting[p.id],
        )
        for p in patients
    ]


@router.post("/{patient_id}/transfer", response=PatientOut)
def transfer_patient(request, patient_id: int, data: TransferIn):
    """Traspasa uno de tus pacientes a otro usuario (los pacientes no se crean desde la app)."""
    patient = get_object_or_404(services.patients_of(request.user), pk=patient_id)
    target = (
        get_user_model().objects.filter(email__iexact=data.to_email.strip(), is_active=True).first()
    )
    if target is None:
        raise HttpError(404, "No existe una cuenta activa con ese correo.")
    try:
        services.transfer_patient(patient, from_professional=request.user, to_professional=target)
    except services.PatientError as error:
        raise HttpError(409, str(error)) from error
    return patient_out(patient)


@router.get("/{patient_id}/summary", response=PatientSummary)
def get_patient_summary(request, patient_id: int):
    patient = get_object_or_404(services.patients_of(request.user), pk=patient_id)
    return patient_summary(request.user, patient)


@router.get("/{patient_id}/trends", response=list[Trend])
def get_patient_trends(request, patient_id: int):
    """Evolución de exámenes y escalas del paciente (series con al menos dos mediciones)."""
    patient = get_object_or_404(services.patients_of(request.user), pk=patient_id)
    return patient_trends(request.user, patient)


@router.get("/{patient_id}/overview", response=PatientOverview)
def get_patient_overview(request, patient_id: int):
    """Resumen global y síntesis por áreas de la versión oficial vigente del paciente."""
    patient = get_object_or_404(services.patients_of(request.user), pk=patient_id)
    return patient_overview(request.user, patient)


def patient_out(patient) -> PatientOut:
    return PatientOut(
        id=patient.id,
        name=patient.name,
        identifier=patient.identifier,
        bed=patient.bed,
        reference=patient.reference,
    )


class VersionOut(Schema):
    version: int
    reason: str
    isCurrent: bool
    created_at: datetime
    sourceReportId: str | None
    sourceAuthor: str
    sourceProfession: str


@router.get("/{patient_id}/versions", response=list[VersionOut])
def list_patient_versions(request, patient_id: int):
    """Historial de versiones oficiales del paciente: las anteriores nunca se pierden."""
    patient = get_object_or_404(services.patients_of(request.user), pk=patient_id)
    versions = ConsolidatedVersion.objects.filter(patient=patient).select_related(
        "source_report__author"
    )
    return [
        VersionOut(
            version=v.version,
            reason=v.reason,
            isCurrent=v.is_current,
            created_at=v.created_at,
            sourceReportId=str(v.source_report_id) if v.source_report_id else None,
            sourceAuthor=(v.source_report.author.name or v.source_report.author.email)
            if v.source_report
            else "",
            sourceProfession=v.source_report.profession if v.source_report else "",
        )
        for v in versions
    ]


@router.get("/{patient_id}/versions/{version}")
def get_patient_version(request, patient_id: int, version: int):
    """Los datos de una versión oficial concreta (para comparar con la vigente)."""
    patient = get_object_or_404(services.patients_of(request.user), pk=patient_id)
    found = get_object_or_404(ConsolidatedVersion, patient=patient, version=version)
    return {"version": found.version, "reason": found.reason, "data": found.data}


class EvidenceResultIn(Schema):
    name: str
    value: str = ""
    unit: str = ""
    ref_min: str | None = None
    ref_max: str | None = None


class EvidenceIn(Schema):
    kind: str = "lab"
    title: str
    taken_at: datetime
    results: list[EvidenceResultIn] = []
    findings: str = ""


class EvidenceResultOut(Schema):
    name: str
    value: str
    unit: str
    flag: str


class EvidenceOut(Schema):
    id: int
    kind: str
    title: str
    takenAt: datetime
    results: list[EvidenceResultOut]
    findings: str
    createdByName: str


def _evidence_out(item) -> EvidenceOut:
    return EvidenceOut(
        id=item.id,
        kind=item.kind,
        title=item.title,
        takenAt=item.taken_at,
        results=[
            EvidenceResultOut(name=r["name"], value=r["value"], unit=r["unit"], flag=r["flag"])
            for r in item.results
        ],
        findings=item.findings,
        createdByName=item.created_by.name or item.created_by.email,
    )


@router.get("/{patient_id}/evidence", response=list[EvidenceOut])
def list_patient_evidence(request, patient_id: int):
    """Exámenes y otra evidencia del paciente, además de los dictados."""
    try:
        return [
            _evidence_out(item)
            for item in evidence_services.list_evidence(request.user, patient_id)
        ]
    except evidence_services.EvidenceError as error:
        raise HttpError(404, str(error)) from error


@router.post("/{patient_id}/evidence", response={201: EvidenceOut})
def add_patient_evidence(request, patient_id: int, data: EvidenceIn):
    """Carga evidencia; los informes por validar del paciente se revisan de nuevo con ella."""
    try:
        item = evidence_services.add_evidence(
            request.user,
            patient_id,
            kind=data.kind,
            title=data.title,
            taken_at=data.taken_at,
            results=[r.dict() for r in data.results],
            findings=data.findings,
        )
    except evidence_services.EvidenceError as error:
        raise HttpError(400, str(error)) from error
    return 201, _evidence_out(item)
