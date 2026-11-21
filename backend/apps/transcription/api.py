"""Endpoints del módulo de transcripción, montados en `/-/api/transcription/`."""

from ninja import File, Router
from ninja.errors import HttpError
from ninja.files import UploadedFile

from .services import TranscriptionOut, ingest_audio, list_transcriptions

router = Router(tags=["transcription"])


@router.get("/transcripts", response=list[TranscriptionOut])
def list_transcripts(request):
    return list_transcriptions()


@router.post("/audios", response={201: TranscriptionOut})
def upload_audio(request, file: UploadedFile = File(...)):
    try:
        transcription = ingest_audio(file.name or "audio.wav", file.content_type or "", file.read())
    except ValueError as error:
        raise HttpError(400, str(error)) from error
    return 201, transcription
