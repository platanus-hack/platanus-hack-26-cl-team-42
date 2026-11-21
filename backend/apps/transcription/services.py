"""Transcripción automática de los dictados.

Flujo: al guardar un dictado se crea su transcripción *pendiente* y se encola en
Celery -> el worker decodifica el audio a PCM mono de 16 kHz -> lo transcribe con
Whisper (modelo gratuito de Hugging Face) -> guarda el texto ligado al dictado.
Si algo falla queda en estado *error* y se puede reintentar.
"""

import io
import logging
import shutil
import subprocess
import wave
from datetime import datetime
from functools import cache
from pathlib import Path
from typing import Any, BinaryIO

from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import transaction
from django.utils import timezone
from pydantic import BaseModel

from apps.recordings.models import Recording
from apps.recordings.services import create_recording

from .models import Transcription

logger = logging.getLogger(__name__)

DEFAULT_MODEL_ID = "openai/whisper-small"
DEFAULT_LANGUAGE = "spanish"
SAMPLES_DIR = Path(__file__).parent / "samples"
WHISPER_SAMPLE_RATE = 16000
FFMPEG_TIMEOUT_SECONDS = 600


class TranscriptionOut(BaseModel):
    """Transcripción con los datos de su dictado (formato del frontend)."""

    id: str
    recordingId: str
    name: str
    patientReference: str
    recordedAt: datetime
    durationSeconds: float | None
    status: str
    language: str
    text: str
    error: str
    created_at: datetime


class TranscriptionError(ValueError):
    """El audio no se pudo preparar para transcribirlo."""


def request_transcription(recording: Recording) -> Transcription:
    """Deja la transcripción del dictado en *pendiente* y la encola al confirmar la transacción.

    Sirve tanto para la primera transcripción como para reintentar una fallida.
    """
    transcription, _ = Transcription.objects.update_or_create(
        recording=recording,
        defaults={
            "status": Transcription.Status.PENDING,
            "text": "",
            "error": "",
            "language": DEFAULT_LANGUAGE,
            "model_id": DEFAULT_MODEL_ID,
        },
    )
    transaction.on_commit(lambda: _enqueue(transcription.id))
    return transcription


def run_transcription(transcription_id: int) -> str:
    """Transcribe el audio del dictado y guarda el resultado (lo ejecuta el worker)."""
    transcription = Transcription.objects.select_related("recording").get(pk=transcription_id)
    if transcription.status == Transcription.Status.DONE:
        return transcription.status
    transcription.status = Transcription.Status.PROCESSING
    transcription.save(update_fields=["status", "updated_at"])
    try:
        with transcription.recording.audio.open("rb") as audio_file:
            text = transcribe(audio_file)
    except Exception as error:
        logger.exception("Falló la transcripción %s", transcription_id)
        transcription.status = Transcription.Status.FAILED
        transcription.error = _user_message(error)
        transcription.save(update_fields=["status", "error", "updated_at"])
        return transcription.status
    transcription.status = Transcription.Status.DONE
    transcription.text = text
    transcription.error = ""
    transcription.save(update_fields=["status", "text", "error", "updated_at"])
    return transcription.status


def list_transcriptions(professional) -> list[TranscriptionOut]:
    """Transcripciones de los dictados del profesional, más recientes primero."""
    transcriptions = (
        Transcription.objects.filter(recording__professional=professional)
        .select_related("recording")
        .order_by("-recording__recorded_at")
    )
    return [to_out(transcription) for transcription in transcriptions]


def load_sample_audio(
    professional, sample_path: Path = SAMPLES_DIR / "ejemplo.wav"
) -> TranscriptionOut:
    """Crea un dictado con el audio de ejemplo y lo transcribe sin pasar por Celery."""
    recording = create_recording(
        professional=professional,
        audio=SimpleUploadedFile(sample_path.name, sample_path.read_bytes(), "audio/wav"),
        source=Recording.Source.UPLOAD,
        recorded_at=timezone.now(),
        patient_reference="Audio de ejemplo",
    )
    transcription = Transcription.objects.create(
        recording=recording, language=DEFAULT_LANGUAGE, model_id=DEFAULT_MODEL_ID
    )
    run_transcription(transcription.id)
    transcription.refresh_from_db()
    return to_out(transcription)


def transcribe(source: str | Path | BinaryIO) -> str:
    """Devuelve el texto de un audio (ruta o archivo) usando Whisper."""
    transcriber = _get_transcriber(DEFAULT_MODEL_ID)
    output: dict[str, Any] = transcriber(
        _load_audio(source),
        generate_kwargs={"language": DEFAULT_LANGUAGE, "task": "transcribe"},
        return_timestamps=True,  # Soporte para audios largos (> 30s)
    )
    return str(output["text"]).strip()


def to_out(transcription: Transcription) -> TranscriptionOut:
    recording = transcription.recording
    return TranscriptionOut(
        id=str(transcription.id),
        recordingId=str(recording.id),
        name=recording.patient_reference or "Dictado sin paciente",
        patientReference=recording.patient_reference,
        recordedAt=recording.recorded_at,
        durationSeconds=recording.duration_seconds,
        status=transcription.status,
        language="es",
        text=transcription.text,
        error=transcription.error,
        created_at=transcription.created_at,
    )


def _enqueue(transcription_id: int) -> None:
    # Import diferido: tasks importa este módulo.
    from .tasks import transcribe_recording

    transcribe_recording.delay(transcription_id)


def _user_message(error: Exception) -> str:
    if isinstance(error, TranscriptionError):
        return str(error)[:500]
    return "No se pudo transcribir el audio. Intenta nuevamente."


def _load_audio(source: str | Path | BinaryIO) -> dict[str, Any]:
    """Audio como muestras mono de 16 kHz, el formato que espera Whisper.

    Los WAV ya compatibles se leen directo; el resto (webm/opus, mp4/aac, mp3…)
    se convierte con ffmpeg.
    """
    data = Path(source).read_bytes() if isinstance(source, str | Path) else source.read()
    try:
        return _read_wav(io.BytesIO(data))
    except TranscriptionError:
        return _decode_with_ffmpeg(data)


def _read_wav(source: BinaryIO) -> dict[str, Any]:
    """Lee un WAV mono de 16 kHz y 16 bits sin depender de ffmpeg."""
    try:
        with wave.open(source, "rb") as wav:
            if (
                wav.getframerate() != WHISPER_SAMPLE_RATE
                or wav.getnchannels() != 1
                or wav.getsampwidth() != 2
            ):
                raise TranscriptionError("El WAV no es mono de 16 kHz y 16 bits")
            frames = wav.readframes(wav.getnframes())
    except (wave.Error, EOFError) as error:
        raise TranscriptionError(f"Archivo WAV no válido: {error}") from error
    return _pcm_to_samples(frames)


def _decode_with_ffmpeg(data: bytes) -> dict[str, Any]:
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg is None:
        raise TranscriptionError(
            "El servidor no tiene ffmpeg para convertir este formato de audio."
        )
    command = [
        ffmpeg, "-nostdin", "-loglevel", "error", "-i", "pipe:0",
        "-ac", "1", "-ar", str(WHISPER_SAMPLE_RATE), "-f", "s16le", "pipe:1",
    ]  # fmt: skip
    try:
        result = subprocess.run(
            command, input=data, capture_output=True, check=True, timeout=FFMPEG_TIMEOUT_SECONDS
        )
    except subprocess.CalledProcessError as error:
        raise TranscriptionError("El archivo de audio está dañado o no se reconoce.") from error
    if not result.stdout:
        raise TranscriptionError("El audio no contiene sonido.")
    return _pcm_to_samples(result.stdout)


def _pcm_to_samples(frames: bytes) -> dict[str, Any]:
    import numpy as np

    samples = np.frombuffer(frames, dtype=np.int16).astype(np.float32) / 32768.0
    return {"raw": samples, "sampling_rate": WHISPER_SAMPLE_RATE}


@cache
def _get_transcriber(model_id: str) -> Any:
    # Import diferido: transformers/torch son pesados y solo hacen falta al transcribir.
    from transformers import pipeline

    return pipeline("automatic-speech-recognition", model=model_id)
