"""API del módulo de grabaciones. Montada en ``/-/api/recordings``.

Cada profesional ve y gestiona solo sus propios dictados; el audio se
descarga a través de ``/{id}/audio`` (autenticado), nunca por una URL pública.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from django.http import FileResponse
from django.shortcuts import get_object_or_404
from ninja import File, Form, ModelSchema, Router, Schema
from ninja.errors import HttpError
from ninja.files import UploadedFile

from apps.transcription.services import request_transcription

from . import services
from .models import Recording

router = Router(tags=["recordings"])


class RecordingOut(ModelSchema):
    professional_name: str
    audio_path: str

    class Meta:
        model = Recording
        fields = [
            "id",
            "patient_reference",
            "note",
            "profession",
            "specialty",
            "mime_type",
            "size_bytes",
            "duration_seconds",
            "source",
            "recorded_at",
            "created_at",
        ]

    @staticmethod
    def resolve_professional_name(obj: Recording) -> str:
        return obj.professional.name or obj.professional.email

    @staticmethod
    def resolve_audio_path(obj: Recording) -> str:
        return f"/recordings/{obj.id}/audio"


class RecordingIn(Schema):
    source: Recording.Source = Recording.Source.IN_APP
    recorded_at: datetime | None = None
    duration_seconds: float | None = None
    patient_reference: str = ""
    note: str = ""
    profession: str = ""
    specialty: str = ""


@router.get("", response=list[RecordingOut])
def list_recordings(request):
    """Dictados del profesional autenticado, más recientes primero."""
    return Recording.objects.filter(professional=request.user).select_related("professional")


@router.post("", response={201: RecordingOut})
def create_recording(request, audio: File[UploadedFile], data: Form[RecordingIn]):
    try:
        recording = services.create_recording(
            professional=request.user,
            audio=audio,
            source=data.source,
            recorded_at=data.recorded_at,
            duration_seconds=data.duration_seconds,
            patient_reference=data.patient_reference,
            note=data.note,
            profession=data.profession,
            specialty=data.specialty,
        )
    except services.RecordingError as error:
        raise HttpError(400, str(error)) from error
    # Paso 2 del flujo: el dictado pasa de inmediato a transcribirse en segundo plano.
    request_transcription(recording)
    return 201, recording


@router.get("/{recording_id}", response=RecordingOut)
def get_recording(request, recording_id: UUID):
    return _own_recording(request, recording_id)


@router.get("/{recording_id}/audio")
def download_audio(request, recording_id: UUID):
    recording = _own_recording(request, recording_id)
    response = FileResponse(recording.audio.open("rb"), content_type=recording.mime_type)
    response["Cache-Control"] = "private, no-store"
    return response


@router.delete("/{recording_id}", response={204: None})
def delete_recording(request, recording_id: UUID):
    services.delete_recording(_own_recording(request, recording_id))
    return 204, None


def _own_recording(request, recording_id: UUID) -> Recording:
    return get_object_or_404(
        Recording.objects.select_related("professional"),
        pk=recording_id,
        professional=request.user,
    )
