"""Extracción de información estructurada desde transcripciones usando Qwen + templates."""

import json
import logging
from typing import Any

from apps.agent.llm import ChatMessage, ModelError
from apps.agent.registry import get_chat_model
from apps.clinical_templates import services as template_services
from apps.recordings.models import Recording

from .models import ExtractedRecord, Transcription

logger = logging.getLogger(__name__)

DEFAULT_EXTRACTION_MODEL = "qwen-local"


def request_extraction(recording: Recording, template_slug: str) -> ExtractedRecord | None:
    """Encola la extracción de información para una grabación.

    Solo crea ExtractedRecord si la transcripción existe y está completa.
    """
    try:
        transcription = recording.transcription
    except Transcription.DoesNotExist:
        return None

    if transcription.status != Transcription.Status.DONE:
        return None

    try:
        template = template_services.get_active_template(template_slug)
    except Exception as error:
        logger.error(f"Template not found: {template_slug}: {error}")
        return None

    record, _ = ExtractedRecord.objects.update_or_create(
        transcription=transcription,
        defaults={
            "template": template,
            "status": ExtractedRecord.Status.PENDING,
            "data": None,
            "error": "",
        },
    )
    # Encolar tarea después de confirmar transacción
    from django.db import transaction
    transaction.on_commit(lambda: _enqueue(record.id))
    return record


def run_extraction(record_id: int) -> str:
    """Extrae información estructurada de una transcripción (lo ejecuta el worker)."""
    record = ExtractedRecord.objects.select_related("transcription", "template").get(pk=record_id)

    if record.status == ExtractedRecord.Status.DONE:
        return record.status

    record.status = ExtractedRecord.Status.PROCESSING
    record.save(update_fields=["status", "updated_at"])

    try:
        text = record.transcription.text
        if not text:
            raise ValueError("Transcripción vacía")

        extracted = _extract_with_qwen(
            text,
            record.template.output_schema,
            record.template.llm_instructions,
        )

        # Validar contra schema
        issues = template_services.validate_record(record.template, extracted)
        if issues:
            error_msg = "; ".join(f"{issue.path}: {issue.message}" for issue in issues[:3])
            raise ValueError(f"Validación fallida: {error_msg}")

        record.status = ExtractedRecord.Status.DONE
        record.data = extracted
        record.error = ""
    except Exception as error:
        logger.exception("Extracción falló para record %s", record_id)
        record.status = ExtractedRecord.Status.FAILED
        record.error = str(error)[:500]

    record.save(update_fields=["status", "data", "error", "updated_at"])
    return record.status


def _extract_with_qwen(
    transcript: str,
    output_schema: dict[str, Any],
    instructions: str,
) -> dict[str, Any]:
    """Usa Qwen para extraer información estructurada del transcript."""
    model = get_chat_model(DEFAULT_EXTRACTION_MODEL)

    prompt = f"""{instructions}

Transcript a procesar:
{transcript}

Responde SIEMPRE como JSON válido que siga exactamente el schema JSON proporcionado."""

    messages = [
        ChatMessage(role="system", content=json.dumps(output_schema)),
        ChatMessage(role="user", content=prompt),
    ]

    try:
        response = model.complete(messages)
    except ModelError as error:
        raise ValueError(f"Error del modelo: {error}") from error

    # Parsear JSON de la respuesta
    try:
        # Buscar JSON dentro de la respuesta
        start, end = response.find("{"), response.rfind("}")
        if start == -1 or end <= start:
            raise ValueError(f"No se encontró JSON en respuesta: {response[:100]}")
        extracted = json.loads(response[start:end+1])
        return extracted if isinstance(extracted, dict) else {}
    except (json.JSONDecodeError, ValueError) as error:
        raise ValueError(f"JSON inválido en respuesta: {error}") from error


def _enqueue(record_id: int) -> None:
    # Import diferido: tasks importa este módulo
    from .tasks import extract_record_information
    extract_record_information.delay(record_id)
