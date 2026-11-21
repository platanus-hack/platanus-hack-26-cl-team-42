"""Módulo 1 · Obtención de datos: los dictados de audio de cada profesional.

``Recording`` corresponde a la entidad *Dictado* del modelo de datos: el audio
crudo que un profesional graba (o sube) mientras examina a un paciente. La
transcripción y la extracción de registros clínicos ocurren en etapas
posteriores y referencian este modelo.

El audio es información clínica sensible (Ley 20.584): se guarda fuera de
``MEDIA_URL`` público y solo se sirve a través de la API autenticada.
"""

import uuid

from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _


def recording_upload_path(instance: "Recording", filename: str) -> str:
    """Store audio under an opaque name so the original filename never leaks."""
    extension = filename.rsplit(".", 1)[-1].lower() if "." in filename else "bin"
    return f"recordings/{instance.professional_id}/{instance.id}.{extension}"


class Recording(models.Model):
    """Un dictado de audio, asociado al profesional que lo grabó."""

    class Source(models.TextChoices):
        IN_APP = "in_app", _("Recorded in app")
        UPLOAD = "upload", _("Uploaded file")

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    professional = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="recordings",
    )
    # Referencia libre al paciente/cama elegido antes de grabar. Se reemplazará
    # por una FK a Episodio cuando ese modelo exista.
    patient_reference = models.CharField(max_length=120, blank=True)
    note = models.CharField(max_length=255, blank=True)

    audio = models.FileField(upload_to=recording_upload_path)
    mime_type = models.CharField(max_length=100)
    size_bytes = models.PositiveBigIntegerField()
    duration_seconds = models.FloatField(null=True, blank=True)
    source = models.CharField(max_length=10, choices=Source.choices)

    # Hora en que comenzó la captura (cliente); puede diferir de created_at si
    # el audio se sube más tarde.
    recorded_at = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-recorded_at"]

    def __str__(self) -> str:
        return f"Recording {self.id} by {self.professional_id} ({self.recorded_at:%Y-%m-%d %H:%M})"
