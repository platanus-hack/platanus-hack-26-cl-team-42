"""Módulo 2 · Transcripción automática de los dictados.

Cada ``Recording`` (dictado) tiene a lo más una ``Transcription``. Se crea en
estado *pendiente* al guardar el dictado y un worker de Celery la completa con
Whisper. El audio sigue viviendo en el dictado: aquí solo se guarda el texto.
"""

from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.recordings.models import Recording


class Transcription(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", _("Pending")
        PROCESSING = "processing", _("Processing")
        DONE = "done", _("Done")
        FAILED = "failed", _("Failed")

    recording = models.OneToOneField(
        Recording, on_delete=models.CASCADE, related_name="transcription"
    )
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.PENDING)
    text = models.TextField(blank=True)
    language = models.CharField(max_length=20)
    model_id = models.CharField(max_length=255)
    # Mensaje para el profesional cuando la transcripción falla.
    error = models.CharField(max_length=500, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self) -> str:
        return f"Transcripción de {self.recording_id} ({self.status})"
