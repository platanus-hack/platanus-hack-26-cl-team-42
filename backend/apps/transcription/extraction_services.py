"""Extracción de registros clínicos estructurados desde transcripciones con un LLM.

Flujo: transcripción lista + plantilla (la del tipo de profesional del dictado) ->
``ExtractedRecord`` pendiente y tarea de Celery -> el modelo responde un JSON según el
schema de la plantilla, y mientras lo genera se va guardando lo ya leído para mostrar
cómo se llena -> se valida (con un reintento que devuelve los errores al modelo) -> se
guarda. Las secciones con información pendiente se pueden completar después con texto
o con otro audio (``request_section_update``).
"""

import json
import logging
import time
import unicodedata
from collections.abc import Callable
from datetime import datetime, timedelta
from typing import Any

from decouple import config
from django.core.files.storage import default_storage
from django.db import transaction
from django.utils import timezone
from pydantic import BaseModel

from apps.agent.llm import ChatMessage, ChatModel, ModelError
from apps.agent.registry import available_models, get_chat_model
from apps.clinical_templates import services as template_services
from apps.clinical_templates.models import ClinicalTemplate
from apps.recordings.models import Recording

from . import pipeline_cache
from .models import ExtractedRecord, Report, Transcription
from .partial_json import parse_partial_json_object

logger = logging.getLogger(__name__)

# Primer modelo disponible en este orden; EXTRACTION_MODEL fuerza uno concreto.
MODEL_PREFERENCE = ("claude", "qwen-hf", "qwen-local")
MAX_ATTEMPTS = 2
MAX_ISSUES_IN_FEEDBACK = 10
PROGRESS_INTERVAL_SECONDS = 1.0
# Una extracción "en curso" más antigua que esto se da por perdida (p. ej. worker reiniciado).
IN_PROGRESS_TIMEOUT = timedelta(minutes=10)

Validator = Callable[[dict[str, Any]], list[template_services.ValidationIssue]]
ProgressCallback = Callable[[dict[str, Any]], None]


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
    """No se pudo pedir la extracción (transcripción no lista, plantilla o sección inválida)."""


def request_extraction(
    transcription: Transcription, template_slug: str | None = None
) -> ExtractedRecord:
    """Deja el registro en *pendiente* y lo encola al confirmar la transacción.

    Sin ``template_slug`` la plantilla se elige según el tipo de profesional del
    dictado. Si ya hay una extracción reciente en curso con esa plantilla, la devuelve
    tal cual en vez de lanzar otra.
    """
    if transcription.status != Transcription.Status.DONE or not transcription.text.strip():
        raise ExtractionError("La transcripción aún no está lista.")
    template = _resolve_template(transcription.recording, template_slug)

    existing = ExtractedRecord.objects.filter(transcription=transcription).first()
    if existing and existing.template_id == template.id and _in_progress(existing):
        return existing

    record, _ = ExtractedRecord.objects.update_or_create(
        transcription=transcription,
        defaults={
            "template": template,
            "status": ExtractedRecord.Status.PENDING,
            "data": None,
            "error": "",
        },
    )
    _reset_report(record)
    transaction.on_commit(lambda: _enqueue(record.id))
    return record


def request_automatic_extraction(transcription: Transcription) -> ExtractedRecord | None:
    """Encola el parseo con la plantilla del dictado, identificándola si no se indicó.

    Si el dictado no trae el tipo de profesional, se deduce del contenido de la transcripción
    (y se guarda en el dictado). Si no se logra identificar, no hace nada.
    """
    recording = transcription.recording
    if not recording.profession:
        profession = identify_profession(transcription)
        if profession is None:
            logger.warning("No se identificó la plantilla de la transcripción %s", transcription.id)
            return None
        recording.profession = profession
        recording.save(update_fields=["profession"])
    try:
        return request_extraction(transcription)
    except ExtractionError:
        logger.warning("Sin extracción automática para la transcripción %s", transcription.id)
        return None


def run_extraction(record_id: int) -> str:
    """Extrae el registro estructurado de la transcripción (lo ejecuta el worker)."""
    record = ExtractedRecord.objects.select_related("transcription", "template").get(pk=record_id)
    if record.status == ExtractedRecord.Status.DONE:
        return record.status
    record.status = ExtractedRecord.Status.PROCESSING
    record.save(update_fields=["status", "updated_at"])

    def save_progress(partial: dict[str, Any]) -> None:
        record.data = partial
        record.save(update_fields=["data", "updated_at"])

    try:
        record.data = _extract(record.transcription, record.template, save_progress)
    except Exception as error:
        logger.exception("Falló la extracción %s", record_id)
        record.status = ExtractedRecord.Status.FAILED
        record.error = str(error)[:500]
    else:
        record.status = ExtractedRecord.Status.DONE
        record.error = ""
    record.save(update_fields=["status", "data", "error", "updated_at"])
    if record.status == ExtractedRecord.Status.DONE:
        _build_report(record)
    return record.status


@transaction.atomic
def request_section_update(
    record: ExtractedRecord, section: str, text: str = "", audio=None
) -> ExtractedRecord:
    """Encola la incorporación de información nueva (escrita y/o en audio) a una sección."""
    report = Report.objects.select_for_update().filter(extracted_record=record).first()
    record.refresh_from_db(from_queryset=ExtractedRecord.objects.select_for_update())
    if record.status != ExtractedRecord.Status.DONE or not record.data:
        raise ExtractionError("El registro aún no está listo para completarse.")
    if report and report.status == Report.Status.DONE:
        raise ExtractionError("El informe ya fue guardado y no se puede editar.")
    if section not in record.template.output_schema["properties"]:
        raise ExtractionError(f"La plantilla no tiene la sección '{section}'.")
    text = text.strip()
    if not text and audio is None:
        raise ExtractionError("Escribe o graba la información que falta.")

    audio_name = ""
    if audio is not None:
        extension = audio.name.rsplit(".", 1)[-1].lower() if "." in (audio.name or "") else "bin"
        audio_name = default_storage.save(f"complements/{record.id}-{section}.{extension}", audio)

    record.status = ExtractedRecord.Status.PROCESSING
    record.error = ""
    record.save(update_fields=["status", "error", "updated_at"])
    transaction.on_commit(lambda: _enqueue_section_update(record.id, section, text, audio_name))
    return record


def run_section_update(record_id: int, section: str, text: str, audio_name: str) -> str:
    """Incorpora la información nueva a una sección del registro (lo ejecuta el worker)."""
    record = ExtractedRecord.objects.select_related("transcription", "template").get(pk=record_id)
    try:
        if audio_name:
            text = f"{text}\n{_transcribe_stored_audio(audio_name)}".strip()
        current = record.data or {}
        updated = _extract_section(record, section, text)[section]
        record.data = {**current, section: _keep_existing(current.get(section), updated)}
        record.error = ""
    except Exception as error:
        logger.exception("Falló completar la sección %s del registro %s", section, record_id)
        record.error = f"No se pudo incorporar la información: {error}"[:500]
    finally:
        if audio_name:
            default_storage.delete(audio_name)
    # El registro sigue «en curso» hasta que el informe quedó rehomologado: así quien lo mira
    # espera a que todo el flujo (transcribir, parsear, homologar) termine.
    record.save(update_fields=["data", "error", "updated_at"])
    _build_report(record, changed_section=section)
    record.status = ExtractedRecord.Status.DONE
    record.save(update_fields=["status", "updated_at"])
    return record.status


def identify_profession(transcription: Transcription) -> str | None:
    """Tipo de profesional que dictó (``ClinicalTemplate.Profession``), deducido del texto.

    Los audios de demo conocidos traen su profesional en `samples/transcripts.json`;
    si no, lo decide el modelo y, si no responde bien, unas palabras clave. El resultado se cachea.
    """
    known = _known_profession(transcription.recording)
    if known:
        return known
    key = pipeline_cache.cache_key(transcription.text)
    cached = pipeline_cache.load("profession", key)
    if cached is not None:
        return cached.get("profession")

    text = transcription.text
    profession = _identify_with_model(text) or _identify_by_keywords(text)
    if profession:
        pipeline_cache.store("profession", key, {"profession": profession})
    return profession


def complete_json(messages: list[ChatMessage]) -> dict[str, Any]:
    """Respuesta JSON del modelo de extracción a una conversación (una sola vuelta)."""
    try:
        reply = _extraction_model().complete(messages)
    except ModelError as error:
        raise ValueError(f"Error del modelo: {error}") from error
    parsed = _parse_json_object(reply)
    if parsed is None:
        raise ValueError("El modelo no respondió un JSON válido.")
    return parsed


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


def _in_progress(record: ExtractedRecord) -> bool:
    active = record.status in (ExtractedRecord.Status.PENDING, ExtractedRecord.Status.PROCESSING)
    return active and timezone.now() - record.updated_at < IN_PROGRESS_TIMEOUT


def _resolve_template(recording: Recording, template_slug: str | None) -> ClinicalTemplate:
    try:
        if template_slug:
            return template_services.get_active_template(template_slug)
        if not recording.profession:
            raise ExtractionError("El dictado no indica el profesional: elige una plantilla.")
        return template_services.get_active_template_for_profession(recording.profession)
    except ClinicalTemplate.DoesNotExist as error:
        raise ExtractionError("No existe la plantilla pedida.") from error


def _extract(
    transcription: Transcription, template: ClinicalTemplate, on_progress: ProgressCallback
) -> dict[str, Any]:
    messages = [
        ChatMessage(role="system", content=_system_prompt(template)),
        ChatMessage(role="user", content=_user_prompt(transcription)),
    ]

    def validate(record: dict[str, Any]) -> list[template_services.ValidationIssue]:
        return template_services.validate_record(template, record)

    # Mismo texto y plantilla => mismo registro: no se vuelve a llamar al modelo.
    recording = transcription.recording
    key = pipeline_cache.cache_key(template.slug, template.content_hash, transcription.text)
    cached = pipeline_cache.load("extraction", key)
    if cached is not None:
        return _refresh_metadata(cached, recording)
    record = _ask_for_json(messages, validate, on_progress)
    pipeline_cache.store("extraction", key, record)
    return record


def _extract_section(record: ExtractedRecord, section: str, new_information: str) -> dict[str, Any]:
    """``{"<sección>": valor}`` con la sección actualizada con la información nueva."""
    template = record.template
    schema = json.dumps(template_services.section_schema(template, section), ensure_ascii=False)
    current = json.dumps((record.data or {}).get(section), ensure_ascii=False)
    messages = [
        ChatMessage(
            role="system",
            content=(
                f"{template.llm_instructions}\n\n"
                f"Ya existe un registro clínico extraído. Actualiza SOLO la sección '{section}' "
                "con la información nueva que entrega el profesional: conserva lo que ya estaba "
                "correcto, completa lo que faltaba y no inventes nada que no se mencione. "
                "Nunca dejes en null ni vacío un valor que ya tenía información, salvo que la "
                "información nueva lo corrija. "
                f'Responde ÚNICAMENTE con un objeto JSON {{"{section}": ...}} que cumpla '
                f"exactamente este JSON Schema:\n{schema}"
            ),
        ),
        ChatMessage(
            role="user",
            content=(
                f"{_dictation_metadata(record.transcription)}\n\n"
                f"Transcripción original:\n\n{record.transcription.text}\n\n"
                f"Información nueva:\n\n{new_information}\n\n"
                f"Valor actual de '{section}':\n{current}"
            ),
        ),
    ]

    def validate(payload: dict[str, Any]) -> list[template_services.ValidationIssue]:
        return template_services.validate_section(template, section, payload)

    # Misma información nueva sobre el mismo valor actual => misma sección: sin llamar al modelo.
    key = pipeline_cache.cache_key(
        template.slug, template.content_hash, section, current, new_information
    )
    cached = pipeline_cache.load("section", key)
    if cached is not None:
        return cached
    updated = _ask_for_json(messages, validate)
    pipeline_cache.store("section", key, updated)
    return updated


def _ask_for_json(
    messages: list[ChatMessage], validate: Validator, on_progress: ProgressCallback | None = None
) -> dict[str, Any]:
    """Pide un JSON válido al modelo; si no lo es, reintenta mostrándole los errores."""
    model = _extraction_model()
    issues: list[template_services.ValidationIssue] = []
    for _ in range(MAX_ATTEMPTS):
        try:
            reply = _complete(model, messages, on_progress)
        except ModelError as error:
            raise ValueError(f"Error del modelo: {error}") from error
        messages.append(ChatMessage(role="assistant", content=reply))

        parsed = _parse_json_object(reply)
        if parsed is None:
            messages.append(
                ChatMessage(role="user", content="Respuesta no válida. Responde solo con el JSON.")
            )
            issues = [template_services.ValidationIssue(path="$", message="Respuesta no JSON")]
            continue
        issues = validate(parsed)
        if not issues:
            return parsed
        feedback = "\n".join(f"- {i.path}: {i.message}" for i in issues[:MAX_ISSUES_IN_FEEDBACK])
        messages.append(
            ChatMessage(
                role="user",
                content=f"El JSON no cumple el schema:\n{feedback}\nCorrígelo; responde solo JSON.",
            )
        )
    summary = "; ".join(f"{i.path}: {i.message}" for i in issues[:3])
    raise ValueError(f"El modelo no produjo un registro válido. {summary}")


def _complete(
    model: ChatModel, messages: list[ChatMessage], on_progress: ProgressCallback | None
) -> str:
    if on_progress is None or not getattr(model, "streams", False):
        return model.complete(messages)

    last_report = 0.0

    def on_delta(text: str) -> None:
        nonlocal last_report
        if time.monotonic() - last_report < PROGRESS_INTERVAL_SECONDS:
            return
        last_report = time.monotonic()
        partial = parse_partial_json_object(text)
        if partial:
            on_progress(partial)

    return model.complete(messages, on_delta=on_delta)


def _transcribe_stored_audio(audio_name: str) -> str:
    # Import diferido: services importa este módulo.
    from .services import transcribe

    with default_storage.open(audio_name, "rb") as audio_file:
        return transcribe(audio_file)


def _extraction_model() -> ChatModel:
    forced = config("EXTRACTION_MODEL", default="")
    available = available_models()
    return get_chat_model(forced or next(name for name in MODEL_PREFERENCE if name in available))


def _system_prompt(template: ClinicalTemplate) -> str:
    schema = json.dumps(template.output_schema, ensure_ascii=False)
    return (
        f"{template.llm_instructions}\n\n"
        "Responde ÚNICAMENTE con un objeto JSON válido (sin texto adicional ni bloques de código) "
        f"que cumpla exactamente este JSON Schema:\n{schema}"
    )


def _user_prompt(transcription: Transcription) -> str:
    return (
        f"{_dictation_metadata(transcription)}\n\n"
        f"Transcripción del dictado:\n\n{transcription.text}"
    )


def _dictation_metadata(transcription: Transcription) -> str:
    recording = transcription.recording
    known = {
        "Paciente / cama": recording.patient_reference,
        "Especialidad": recording.specialty,
        "Fecha y hora del dictado": recording.recorded_at.isoformat(),
        "Nota": recording.note,
    }
    lines = "\n".join(f"- {label}: {value}" for label, value in known.items() if value)
    return f"Datos del dictado (úsalos para los metadatos del registro):\n{lines}"


def _keep_existing(old: Any, new: Any) -> Any:
    """``new``, pero sin que un valor vacío borre uno que ya tenía información."""
    if isinstance(old, dict) and isinstance(new, dict):
        return {key: _keep_existing(old.get(key), value) for key, value in new.items()}
    if _is_empty(new) and not _is_empty(old):
        return old
    return new


def _is_empty(value: Any) -> bool:
    return value is None or value == "" or value == [] or value == {}


def _parse_json_object(reply: str) -> dict[str, Any] | None:
    start, end = reply.find("{"), reply.rfind("}")
    if start == -1 or end <= start:
        return None
    try:
        parsed = json.loads(reply[start : end + 1])
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


def _refresh_metadata(record: dict[str, Any], recording: Recording) -> dict[str, Any]:
    """Un registro cacheado conserva todo menos los datos de este dictado (hora y cama)."""
    metadata = record.get("metadatos")
    if not isinstance(metadata, dict):
        return record
    metadata = dict(metadata)
    if "fecha_hora_registro" in metadata:
        metadata["fecha_hora_registro"] = recording.recorded_at.isoformat()
    if "cama" in metadata and recording.patient and recording.patient.bed:
        metadata["cama"] = recording.patient.bed
    return {**record, "metadatos": metadata}


def _known_profession(recording: Recording) -> str | None:
    # Import diferido: services importa este módulo.
    from .services import known_profession

    try:
        return known_profession(recording)
    except (OSError, ValueError):
        return None


def _identify_with_model(text: str) -> str | None:
    choices = ClinicalTemplate.Profession.choices
    options = "\n".join(f"- {value}: {label}" for value, label in choices)
    messages = [
        ChatMessage(
            role="system",
            content=(
                "Eres un asistente clínico de una UCI chilena. Lees el dictado de un profesional "
                "y decides quién lo dictó, según el contenido y el vocabulario que usa.\n"
                f"Opciones:\n{options}\n"
                'Responde ÚNICAMENTE con JSON: {"profesion": "<una de las opciones>"}.'
            ),
        ),
        ChatMessage(role="user", content=f"Dictado:\n\n{text[:6000]}"),
    ]
    try:
        profession = complete_json(messages).get("profesion")
    except Exception:
        logger.exception("El modelo no pudo identificar al profesional")
        return None
    valid = {value for value, _ in ClinicalTemplate.Profession.choices}
    return profession if profession in valid else None


# Palabras (sin tildes) que delatan a cada profesional; solo se usan si el modelo falla.
PROFESSION_KEYWORDS = {
    "kinesiologia": ("kinesi", "klgo", "vibropresion", "movilizacion", "ejercicio", "fisioterapia"),
    "enfermeria": ("enfermera", "enfermeria", "curacion", "braden", "balance hidrico"),
    "tens": ("tens", "tecnico en enfermeria", "aseo", "cambio de posicion", "bano en cama"),
    "nutricionista": ("nutricionista", "nutricion", "requerimientos", "formula enteral", "kcal"),
    "especialista": ("interconsulta", "especialista", "infectolog", "cardiolog", "nefrolog"),
    "medico": ("diagnostico", "sepsis", "vasopresor", "sofa", "ventilacion mecanica"),
}


def _identify_by_keywords(text: str) -> str | None:
    plain = unicodedata.normalize("NFKD", text.lower()).encode("ascii", "ignore").decode()
    scores = {
        profession: sum(plain.count(word) for word in words)
        for profession, words in PROFESSION_KEYWORDS.items()
    }
    best = max(scores, key=lambda profession: scores[profession])
    return best if scores[best] > 0 else None


def _build_report(record: ExtractedRecord, changed_section: str | None = None) -> None:
    # Import diferido: report_services importa este módulo.
    from . import report_services

    try:
        report_services.generate_report(record, changed_section)
    except Exception:
        # El registro ya quedó listo: un fallo del informe no debe deshacerlo.
        logger.exception("No se pudo generar el informe del registro %s", record.id)


def _reset_report(record: ExtractedRecord) -> None:
    from . import report_services

    report_services.reset_report(record)


def _enqueue(record_id: int) -> None:
    # Import diferido: tasks importa este módulo.
    from .tasks import extract_record_information

    extract_record_information.delay(record_id)


def _enqueue_section_update(record_id: int, section: str, text: str, audio_name: str) -> None:
    from .tasks import update_record_section

    update_record_section.delay(record_id, section, text, audio_name)
