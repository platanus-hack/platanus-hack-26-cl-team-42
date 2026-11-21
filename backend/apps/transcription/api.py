"""Endpoints del módulo de transcripción, montados en `/-/api/transcription/`.

Las transcripciones se crean solas al guardar un dictado (ver
``apps.recordings.api``); aquí se consultan y se reintentan las fallidas.
Cada profesional solo ve las de sus propios dictados.
"""

from uuid import UUID

from django.shortcuts import get_object_or_404
from ninja import Router
from ninja.errors import HttpError

from apps.recordings.models import Recording

from .models import Transcription
from .services import TranscriptionOut, list_transcriptions, request_transcription, to_out

router = Router(tags=["transcription"])


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
