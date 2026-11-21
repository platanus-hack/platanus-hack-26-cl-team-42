"""Transcripción automática de audios cargados.

Flujo: el audio entra y se guarda en la base de datos -> se transcribe con Whisper
(modelo gratuito de Hugging Face) -> la transcripción queda ligada a la metadata del
audio -> se borra el contenido binario del audio y quedan solo metadata y texto.
"""

import io
import wave
from datetime import datetime
from functools import cache
from pathlib import Path
from typing import Any, BinaryIO

from django.db import transaction
from pydantic import BaseModel

from .models import Audio, Transcription

DEFAULT_MODEL_ID = "openai/whisper-small"
DEFAULT_LANGUAGE = "spanish"
SAMPLES_DIR = Path(__file__).parent / "samples"
WHISPER_SAMPLE_RATE = 16000


class TranscriptionOut(BaseModel):
    """Transcripción con la metadata de su audio (formato del frontend)."""

    id: str
    recordingId: str
    name: str
    status: str
    language: str
    text: str
    created_at: datetime


def ingest_audio(name: str, content_type: str, data: bytes) -> TranscriptionOut:
    """Guarda el audio, lo transcribe y borra su contenido al quedar la transcripción guardada.

    Si la transcripción falla, el audio se queda en la base de datos para reintentarlo.
    """
    audio = Audio.objects.create(
        name=name, content_type=content_type, size_bytes=len(data), data=data
    )
    text = transcribe(io.BytesIO(data))
    with transaction.atomic():
        transcription = Transcription.objects.create(
            audio=audio, text=text, language=DEFAULT_LANGUAGE, model_id=DEFAULT_MODEL_ID
        )
        audio.data = None
        audio.save(update_fields=["data"])
    return _to_out(transcription)


def list_transcriptions() -> list[TranscriptionOut]:
    transcriptions = Transcription.objects.select_related("audio").order_by("-created_at")
    return [_to_out(transcription) for transcription in transcriptions]


def load_sample_audio(sample_path: Path = SAMPLES_DIR / "ejemplo.wav") -> TranscriptionOut:
    """Carga un audio de ejemplo en la base de datos (si no existe ya) y lo transcribe."""
    existing = Transcription.objects.select_related("audio").filter(audio__name=sample_path.name)
    if existing.exists():
        return _to_out(existing.get())
    return ingest_audio(sample_path.name, "audio/wav", sample_path.read_bytes())


def transcribe(source: str | Path | BinaryIO) -> str:
    """Devuelve el texto de un WAV (ruta o archivo) usando Whisper."""
    transcriber = _get_transcriber(DEFAULT_MODEL_ID)
    output: dict[str, Any] = transcriber(
        _read_wav(source),
        generate_kwargs={"language": DEFAULT_LANGUAGE, "task": "transcribe"},
    )
    return str(output["text"]).strip()


def _to_out(transcription: Transcription) -> TranscriptionOut:
    return TranscriptionOut(
        id=str(transcription.id),
        recordingId=str(transcription.audio_id),
        name=transcription.audio.name,
        status="done",
        language="es",
        text=transcription.text,
        created_at=transcription.created_at,
    )


def _read_wav(source: str | Path | BinaryIO) -> dict[str, Any]:
    """Lee un WAV mono de 16 kHz y 16 bits sin depender de ffmpeg."""
    import numpy as np

    try:
        with wave.open(source if isinstance(source, io.IOBase) else str(source), "rb") as wav:
            if (
                wav.getframerate() != WHISPER_SAMPLE_RATE
                or wav.getnchannels() != 1
                or wav.getsampwidth() != 2
            ):
                raise ValueError(
                    "Se esperaba un WAV mono de 16 kHz y 16 bits (otros formatos requieren ffmpeg)"
                )
            frames = wav.readframes(wav.getnframes())
    except wave.Error as error:
        raise ValueError(f"Archivo WAV no válido: {error}") from error
    samples = np.frombuffer(frames, dtype=np.int16).astype(np.float32) / 32768.0
    return {"raw": samples, "sampling_rate": WHISPER_SAMPLE_RATE}


@cache
def _get_transcriber(model_id: str) -> Any:
    # Import diferido: transformers/torch son pesados y solo hacen falta al transcribir.
    from transformers import pipeline

    return pipeline("automatic-speech-recognition", model=model_id)
