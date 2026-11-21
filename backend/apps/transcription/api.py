"""Endpoints del módulo de transcripción, montados en `/-/api/transcription/`.

Las transcripciones se crean solas al guardar un dictado (ver
``apps.recordings.api``); aquí se consultan y se reintentan las fallidas.
Cada profesional solo ve las de sus propios dictados.
"""

from uuid import UUID

from django.shortcuts import get_object_or_404
from ninja import File, Form, Router, Schema
from ninja.errors import HttpError
from ninja.files import UploadedFile

from apps.recordings.models import Recording
from apps.recordings.services import ALLOWED_MIME_TYPES, MAX_AUDIO_BYTES, base_mime_type

from . import reconciliation_services, report_assistant, report_services
from .extraction_services import (
    ExtractionError,
    ExtractionOut,
    list_extractions,
    request_extraction,
    request_section_update,
)
from .extraction_services import to_out as extraction_to_out
from .homologation_services import list_mappings
from .models import ExtractedRecord, Transcription
from .report_services import PipelineOut, ReportOut, get_pipeline, get_report, list_reports
from .services import (
    TranscriptionOut,
    list_transcriptions,
    request_transcription,
    to_out,
)

router = Router(tags=["transcription"])


class ConceptMappingOut(Schema):
    id: str
    sourceTerm: str
    sourceProfessional: str
    suggestedConcept: str | None
    approvedConcept: str | None
    status: str


class ComplementIn(Schema):
    section: str
    text: str = ""


class ExtractIn(Schema):
    # Sin plantilla se elige la del tipo de profesional del dictado.
    template_slug: str | None = None


@router.get("/transcripts", response=list[TranscriptionOut])
def list_transcripts(request):
    return list_transcriptions(request.user)


@router.get("/recordings/{recording_id}", response=TranscriptionOut)
def get_recording_transcript(request, recording_id: UUID):
    transcription = get_object_or_404(
        Transcription.objects.select_related("recording"),
        recording_id=recording_id,
        recording__professional=request.user,
    )
    return to_out(transcription)


@router.post("/recordings/{recording_id}", response={202: TranscriptionOut})
def transcribe_recording(request, recording_id: UUID):
    """Encola (o reintenta) la transcripción de un dictado."""
    recording = get_object_or_404(Recording, pk=recording_id, professional=request.user)
    existing = Transcription.objects.filter(recording=recording).first()
    if existing and existing.status != Transcription.Status.FAILED:
        raise HttpError(409, "Este dictado ya tiene una transcripción en curso o lista.")
    return 202, to_out(request_transcription(recording))


@router.get("/extractions", response=list[ExtractionOut])
def list_record_extractions(request):
    return list_extractions(request.user)


@router.post("/transcripts/{transcription_id}/extract", response={202: ExtractionOut})
def extract_transcript(request, transcription_id: int, payload: ExtractIn):
    """Encola (o repite) la extracción del registro clínico con la plantilla elegida."""
    transcription = get_object_or_404(
        Transcription.objects.select_related("recording"),
        pk=transcription_id,
        recording__professional=request.user,
    )
    try:
        record = request_extraction(transcription, payload.template_slug)
    except ExtractionError as error:
        raise HttpError(409, str(error)) from error
    return 202, extraction_to_out(record)


@router.post("/extractions/{extraction_id}/complement", response={202: ExtractionOut})
def complement_extraction(
    request,
    extraction_id: int,
    data: Form[ComplementIn],
    audio: UploadedFile | None = File(None),
):
    """Completa una sección del registro con información escrita y/o con otro audio."""
    record = get_object_or_404(
        ExtractedRecord.objects.select_related("template", "transcription__recording"),
        pk=extraction_id,
        transcription__recording__professional=request.user,
    )
    if audio is not None:
        if base_mime_type(audio.content_type) not in ALLOWED_MIME_TYPES:
            raise HttpError(400, "Formato de audio no soportado.")
        if audio.size == 0 or audio.size > MAX_AUDIO_BYTES:
            raise HttpError(400, "El audio está vacío o supera el tamaño máximo permitido.")
    try:
        record = request_section_update(record, data.section, data.text, audio)
    except ExtractionError as error:
        raise HttpError(409, str(error)) from error
    return 202, extraction_to_out(record)


@router.get("/recordings/{recording_id}/pipeline", response=PipelineOut)
def get_recording_pipeline(request, recording_id: UUID):
    """Estado de transcripción, parseo e informe de un dictado, en una sola consulta."""
    get_object_or_404(Recording, pk=recording_id, professional=request.user)
    return get_pipeline(recording_id, request.user)


@router.get("/reports", response=list[ReportOut])
def list_user_reports(request, patient_id: int | None = None, include_drafts: bool = False):
    """Informes de tus pacientes (de todos los profesionales) y los tuyos; filtra por paciente."""
    return list_reports(request.user, patient_id, include_drafts)


@router.get("/reports/{report_id}", response=ReportOut)
def get_user_report(request, report_id: int):
    report = get_report(request.user, report_id)
    if report is None:
        raise HttpError(404, "Informe no encontrado.")
    return report


@router.get("/concepts", response=list[ConceptMappingOut])
def list_concept_mappings(request):
    """Términos homologados y el representante común al que se llevan."""
    return [
        ConceptMappingOut(
            id=str(mapping.id),
            sourceTerm=mapping.original_term,
            sourceProfessional=mapping.profession,
            suggestedConcept=mapping.concept.canonical,
            approvedConcept=(
                mapping.concept.canonical if mapping.status == mapping.Status.APPROVED else None
            ),
            status=mapping.status,
        )
        for mapping in list_mappings()
    ]


class AskIn(Schema):
    question: str
    patient_id: int | None = None


@router.post("/assistant/ask", response=report_assistant.AssistantAnswer)
def ask_assistant(request, payload: AskIn):
    """Responde sobre tus informes (o los de un paciente) citando informe y sección."""
    try:
        return report_assistant.ask(request.user, payload.question, payload.patient_id)
    except report_assistant.AssistantError as error:
        raise HttpError(422, str(error)) from error


@router.post("/reports/{report_id}/validate", response=ReportOut)
def validate_user_report(request, report_id: int):
    """El autor guarda el informe con todos sus temas validados: ya no se puede editar."""
    report = get_object_or_404(
        report_services.visible_reports(request.user), pk=report_id, author=request.user
    )
    try:
        report_services.validate_report(report)
    except report_services.ValidationError as error:
        raise HttpError(409, str(error)) from error
    return report_services.to_out(report, request.user)


class TopicValidationIn(Schema):
    validated: bool = True


@router.put("/reports/{report_id}/topics/{topic_id}", response=ReportOut)
def validate_report_topic(request, report_id: int, topic_id: str, payload: TopicValidationIn):
    """El autor valida un tema del informe (o quita la validación)."""
    report = get_object_or_404(
        report_services.visible_reports(request.user), pk=report_id, author=request.user
    )
    try:
        report_services.set_topic_validated(report, topic_id, payload.validated)
    except report_services.ValidationError as error:
        raise HttpError(409, str(error)) from error
    return report_services.to_out(report, request.user)


# --- Reconciliación de conflictos entre informes -------------------------------------------


class NoteIn(Schema):
    body: str


class ChoiceIn(Schema):
    # «a» / «b» (uno de los dos valores) o un valor propio.
    side: str | None = None
    value: str | None = None


class ReplyIn(Schema):
    body: str


@router.get("/reconciliations", response=list[reconciliation_services.ReconciliationOut])
def list_user_reconciliations(request):
    """Reconciliaciones de los pacientes asignados a tu cuenta."""
    return reconciliation_services.list_reconciliations(request.user)


@router.get(
    "/reconciliations/{reconciliation_id}", response=reconciliation_services.ReconciliationOut
)
def get_user_reconciliation(request, reconciliation_id: int):
    found = reconciliation_services.get_reconciliation(request.user, reconciliation_id)
    if found is None:
        raise HttpError(404, "Reconciliación no encontrada.")
    return found


@router.post("/conflicts/{conflict_id}/notes", response=reconciliation_services.ConflictOut)
def add_conflict_note(request, conflict_id: int, payload: NoteIn):
    return _conflict_action(
        request,
        conflict_id,
        lambda c: reconciliation_services.add_note(c, request.user, payload.body),
    )


@router.post("/conflicts/{conflict_id}/accept", response=reconciliation_services.ConflictOut)
def accept_conflict_value(request, conflict_id: int):
    """Aceptas el valor del otro profesional: el conflicto se resuelve al instante."""
    return _conflict_action(
        request, conflict_id, lambda c: reconciliation_services.accept_other(c, request.user)
    )


@router.post("/conflicts/{conflict_id}/propose", response=reconciliation_services.ConflictOut)
def propose_conflict_resolution(request, conflict_id: int, payload: ChoiceIn):
    return _conflict_action(
        request,
        conflict_id,
        lambda c: reconciliation_services.propose(c, request.user, payload.side, payload.value),
    )


@router.post("/conflicts/{conflict_id}/agree", response=reconciliation_services.ConflictOut)
def agree_conflict_proposal(request, conflict_id: int):
    return _conflict_action(
        request, conflict_id, lambda c: reconciliation_services.agree(c, request.user)
    )


@router.post("/conflicts/{conflict_id}/decide", response=reconciliation_services.ConflictOut)
def decide_conflict(request, conflict_id: int, payload: ChoiceIn):
    """Decides solo: el otro profesional está fuera de turno o eres el único participante."""
    return _conflict_action(
        request,
        conflict_id,
        lambda c: reconciliation_services.decide(c, request.user, payload.side, payload.value),
    )


@router.post("/conflicts/{conflict_id}/external", response=reconciliation_services.ConflictOut)
def request_external_opinion(request, conflict_id: int):
    """Pide la opinión externa recomendada: el sistema elige al profesional de turno."""
    return _conflict_action(
        request, conflict_id, lambda c: reconciliation_services.request_external(c, request.user)
    )


@router.get("/external-consults", response=list[reconciliation_services.ExternalConsultOut])
def list_my_external_consults(request):
    """Opiniones externas que te pidieron (con el caso anonimizado)."""
    return reconciliation_services.list_external_consults(request.user)


@router.post(
    "/external-consults/{consult_id}/reply", response=reconciliation_services.ExternalConsultOut
)
def reply_external_consult(request, consult_id: int, payload: ReplyIn):
    consult = reconciliation_services.get_external_consult(request.user, consult_id)
    if consult is None:
        raise HttpError(404, "Consulta no encontrada.")
    try:
        consult = reconciliation_services.reply_external(consult, request.user, payload.body)
    except reconciliation_services.ReconciliationError as error:
        raise HttpError(409, str(error)) from error
    return next(
        c
        for c in reconciliation_services.list_external_consults(request.user)
        if c.id == str(consult.id)
    )


def _conflict_action(request, conflict_id: int, action):
    conflict = reconciliation_services.get_conflict(request.user, conflict_id)
    if conflict is None:
        raise HttpError(404, "Conflicto no encontrado.")
    try:
        action(conflict)
    except reconciliation_services.ReconciliationError as error:
        raise HttpError(409, str(error)) from error
    conflict.refresh_from_db()
    return reconciliation_services.to_conflict_out(conflict, request.user)


@router.post("/reports/{report_id}/alerts/{alert_id}/ack", response=ReportOut)
def acknowledge_report_alert(request, report_id: int, alert_id: str):
    """El autor marca como revisada una alerta de contradicción con la evidencia."""
    report = get_object_or_404(
        report_services.visible_reports(request.user), pk=report_id, author=request.user
    )
    try:
        report_services.acknowledge_alert(report, alert_id)
    except report_services.ValidationError as error:
        raise HttpError(409, str(error)) from error
    return report_services.to_out(report, request.user)
