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

from apps.clinical_templates.models import ClinicalTemplate


def recording_upload_path(instance: "Recording", filename: str) -> str:
    """Store audio under an opaque name so the original filename never leaks."""
    extension = filename.rsplit(".", 1)[-1].lower() if "." in filename else "bin"
    return f"recordings/{instance.professional_id}/{instance.id}.{extension}"


class Patient(models.Model):
    """Paciente al que se asocian dictados e informes; lo ven los profesionales asignados."""

    name = models.CharField(max_length=100)
    # RUT, ficha u otro identificador institucional (opcional; si existe, es único de hecho).
    identifier = models.CharField(max_length=40, blank=True, db_index=True)
    bed = models.CharField(max_length=60, blank=True)
    assigned_to = models.ManyToManyField(
        settings.AUTH_USER_MODEL, related_name="patients", blank=True
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:
        return self.reference

    @property
    def reference(self) -> str:
        """«Juan Pérez (12.345.678-9) · Cama 7»: identifica al paciente en dictados e informes."""
        identified = f"{self.name} ({self.identifier})" if self.identifier else self.name
        return f"{identified} · {self.bed}" if self.bed else identified


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
    # Nombre automático: cuenta · tipo de profesional · fecha y hora de la grabación.
    name = models.CharField(max_length=255, blank=True)
    patient = models.ForeignKey(
        Patient, on_delete=models.PROTECT, null=True, blank=True, related_name="recordings"
    )
    # Texto que identifica al paciente (copia de ``Patient.reference`` o referencia libre antigua).
    patient_reference = models.CharField(max_length=120, blank=True)
    note = models.CharField(max_length=255, blank=True)
    # Tipo de profesional que dicta: define la plantilla clínica con que se
    # estructura la transcripción (ver ``ClinicalTemplate.profession``).
    profession = models.CharField(
        max_length=32, choices=ClinicalTemplate.Profession.choices, blank=True
    )
    specialty = models.CharField(max_length=120, blank=True)

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
