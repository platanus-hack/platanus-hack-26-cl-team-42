"""Extracción de registros clínicos estructurados desde transcripciones con Qwen.

Flujo: transcripción lista + plantilla elegida -> ``ExtractedRecord`` pendiente y
tarea de Celery -> Qwen responde un JSON según el schema de la plantilla -> se
valida (con un reintento que le devuelve los errores al modelo) -> se guarda.
"""

import json
import logging
from datetime import datetime
from typing import Any

from django.db import transaction
from pydantic import BaseModel

from apps.agent.llm import ChatMessage, ChatModel, ModelError
from apps.agent.registry import available_models, get_chat_model
from apps.clinical_templates import services as template_services
from apps.clinical_templates.models import ClinicalTemplate

from .models import ExtractedRecord, Transcription

logger = logging.getLogger(__name__)

API_MODEL_NAME = "qwen-hf"
LOCAL_MODEL_NAME = "qwen-local"
MAX_ATTEMPTS = 2
MAX_ISSUES_IN_FEEDBACK = 10


class ExtractionOut(BaseModel):
    """Registro extraído con los datos de su transcripción (formato del frontend)."""

    id: str
    transcriptId: str
    recordingId: str
    templateSlug: str
    templateName: str
    status: str
    data: dict[str, Any] | None
    error: str
    updated_at: datetime


class ExtractionError(ValueError):
    """No se pudo pedir la extracción (transcripción no lista o plantilla inexistente)."""


def request_extraction(transcription: Transcription, template_slug: str) -> ExtractedRecord:
    """Deja el registro en *pendiente* y lo encola al confirmar la transacción.

    Sirve tanto para la primera extracción como para repetirla con otra plantilla.
    """
    if transcription.status != Transcription.Status.DONE or not transcription.text.strip():
        raise ExtractionError("La transcripción aún no está lista.")
    try:
        template = template_services.get_active_template(template_slug)
    except ClinicalTemplate.DoesNotExist as error:
        raise ExtractionError(f"No existe la plantilla '{template_slug}'.") from error

    record, _ = ExtractedRecord.objects.update_or_create(
        transcription=transcription,
        defaults={
            "template": template,
            "status": ExtractedRecord.Status.PENDING,
            "data": None,
            "error": "",
        },
    )
    transaction.on_commit(lambda: _enqueue(record.id))
    return record


def run_extraction(record_id: int) -> str:
    """Extrae el registro estructurado de la transcripción (lo ejecuta el worker)."""
    record = ExtractedRecord.objects.select_related("transcription", "template").get(pk=record_id)
    if record.status == ExtractedRecord.Status.DONE:
        return record.status
    record.status = ExtractedRecord.Status.PROCESSING
    record.save(update_fields=["status", "updated_at"])
    try:
        record.data = _extract(record.transcription.text, record.template)
    except Exception as error:
        logger.exception("Falló la extracción %s", record_id)
        record.status = ExtractedRecord.Status.FAILED
        record.error = str(error)[:500]
    else:
        record.status = ExtractedRecord.Status.DONE
        record.error = ""
    record.save(update_fields=["status", "data", "error", "updated_at"])
    return record.status


def list_extractions(professional) -> list[ExtractionOut]:
    """Registros extraídos de los dictados del profesional, más recientes primero."""
    records = (
        ExtractedRecord.objects.filter(transcription__recording__professional=professional)
        .select_related("transcription__recording", "template")
        .order_by("-updated_at")
    )
    return [to_out(record) for record in records]


def to_out(record: ExtractedRecord) -> ExtractionOut:
    return ExtractionOut(
        id=str(record.id),
        transcriptId=str(record.transcription_id),
        recordingId=str(record.transcription.recording_id),
        templateSlug=record.template.slug,
        templateName=record.template.name,
        status=record.status,
        data=record.data,
        error=record.error,
        updated_at=record.updated_at,
    )


def _extract(transcript: str, template: ClinicalTemplate) -> dict[str, Any]:
    model = _extraction_model()
    messages = [
        ChatMessage(role="system", content=_system_prompt(template)),
        ChatMessage(role="user", content=f"Transcripción del dictado:\n\n{transcript}"),
    ]
    issues: list[template_services.ValidationIssue] = []
    for _ in range(MAX_ATTEMPTS):
        try:
            reply = model.complete(messages)
        except ModelError as error:
            raise ValueError(f"Error del modelo: {error}") from error
        messages.append(ChatMessage(role="assistant", content=reply))

        record = _parse_json_object(reply)
        if record is None:
            messages.append(
                ChatMessage(role="user", content="Respuesta no válida. Responde solo con el JSON.")
            )
            issues = [template_services.ValidationIssue(path="$", message="La respuesta no es JSON")]
            continue
        issues = template_services.validate_record(template, record)
        if not issues:
            return record
        feedback = "\n".join(f"- {i.path}: {i.message}" for i in issues[:MAX_ISSUES_IN_FEEDBACK])
        messages.append(
            ChatMessage(
                role="user",
                content=f"El JSON no cumple el schema:\n{feedback}\nCorrígelo y responde solo con el JSON.",
            )
        )
    summary = "; ".join(f"{i.path}: {i.message}" for i in issues[:3])
    raise ValueError(f"El modelo no produjo un registro válido. {summary}")


def _extraction_model() -> ChatModel:
    """Qwen por API si está configurado; si no, el Qwen local (mucho menos fiable)."""
    name = API_MODEL_NAME if API_MODEL_NAME in available_models() else LOCAL_MODEL_NAME
    return get_chat_model(name)


def _system_prompt(template: ClinicalTemplate) -> str:
    schema = json.dumps(template.output_schema, ensure_ascii=False)
    return (
        f"{template.llm_instructions}\n\n"
        "Responde ÚNICAMENTE con un objeto JSON válido (sin texto adicional ni bloques de código) "
        f"que cumpla exactamente este JSON Schema:\n{schema}"
    )


def _parse_json_object(reply: str) -> dict[str, Any] | None:
    start, end = reply.find("{"), reply.rfind("}")
    if start == -1 or end <= start:
        return None
    try:
        parsed = json.loads(reply[start : end + 1])
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


def _enqueue(record_id: int) -> None:
    # Import diferido: tasks importa este módulo.
    from .tasks import extract_record_information

    extract_record_information.delay(record_id)
