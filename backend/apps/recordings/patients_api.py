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

from apps.transcription.inbox_services import inbox_states
from apps.transcription.models import ConsolidatedVersion
from apps.transcription.summary_services import PatientSummary, patient_summary

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


@router.get("", response=list[PatientListOut])
def list_patients(request):
    """Pacientes asignados al profesional, con su número de informes y su estado en la bandeja."""
    patients = list(
        services.patients_of(request.user).annotate(
            report_count=Count("reports", filter=Q(reports__status="done"), distinct=True)
        )
    )
    states = inbox_states(request.user, [p.id for p in patients])
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
