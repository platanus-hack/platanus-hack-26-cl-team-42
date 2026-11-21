"""Módulo 2 · Transcripción automática de los dictados.

Cada ``Recording`` (dictado) tiene a lo más una ``Transcription``. Se crea en
estado *pendiente* al guardar el dictado y un worker de Celery la completa con
Whisper. El audio sigue viviendo en el dictado: aquí solo se guarda el texto.

Módulo 3 · Extracción de información estructurada.

Cada ``Transcription`` completada genera un ``ExtractedRecord`` usando Qwen +
templates clínicos. Se guarda en estado *pendiente* y se procesa con Celery.

Módulo 4 · Homologación de conceptos (``Concept``/``ConceptMapping``) e informes
(``Report``): el registro extraído con sus términos unificados, firmado por quien lo generó.
"""

from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.clinical_templates.models import ClinicalTemplate
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


class ExtractedRecord(models.Model):
    """Información estructurada extraída de una transcripción por Qwen."""

    class Status(models.TextChoices):
        PENDING = "pending", _("Pending")
        PROCESSING = "processing", _("Processing")
        DONE = "done", _("Done")
        FAILED = "failed", _("Failed")

    transcription = models.OneToOneField(
        Transcription, on_delete=models.CASCADE, related_name="extracted_record"
    )
    template = models.ForeignKey(ClinicalTemplate, on_delete=models.PROTECT)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.PENDING)
    # Información estructurada según el schema JSON del template
    data = models.JSONField(null=True, blank=True)
    # Errores de validación o procesamiento
    error = models.CharField(max_length=500, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self) -> str:
        return f"Record extraído de {self.transcription_id} ({self.status})"


class Concept(models.Model):
    """Representante común de un concepto clínico (p. ej. «Ventilación mecánica invasiva»)."""

    canonical = models.CharField(max_length=200, unique=True)
    category = models.CharField(max_length=40, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self) -> str:
        return self.canonical


class ConceptMapping(models.Model):
    """Un término tal como lo dicta un profesional y el concepto común al que se homologa."""

    class Source(models.TextChoices):
        SEED = "seed", _("Dictionary")
        MODEL = "model", _("Model")

    class Status(models.TextChoices):
        PENDING = "pending", _("Pending")
        APPROVED = "approved", _("Approved")
        REJECTED = "rejected", _("Rejected")

    # Término normalizado (minúsculas, sin tildes ni espacios sobrantes): clave de búsqueda.
    term = models.CharField(max_length=200, unique=True)
    original_term = models.CharField(max_length=200)
    concept = models.ForeignKey(Concept, on_delete=models.CASCADE, related_name="mappings")
    source = models.CharField(max_length=10, choices=Source.choices)
    # Los del diccionario nacen aprobados; los propuestos por el modelo esperan revisión humana.
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING)
    profession = models.CharField(max_length=32, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["concept__canonical", "term"]

    def __str__(self) -> str:
        return f"{self.original_term} → {self.concept_id}"


class Report(models.Model):
    """Informe de un dictado: el registro extraído con sus conceptos homologados.

    Guarda quién lo generó y cuántos informes de esa categoría profesional tiene el
    paciente (``sequence``: 1 = primero, 2 = segundo…). La consolidación en un estado
    validado actual es una etapa posterior.
    """

    class Status(models.TextChoices):
        PROCESSING = "processing", _("Processing")
        # Homologado y a la espera de que su autor lo revise y lo acepte.
        REVIEW = "review", _("Awaiting validation")
        # Aceptado por su autor: recién entonces el informe cuenta como generado.
        DONE = "done", _("Validated")
        FAILED = "failed", _("Failed")

    extracted_record = models.OneToOneField(
        ExtractedRecord, on_delete=models.CASCADE, related_name="report"
    )
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="reports"
    )
    profession = models.CharField(max_length=32, choices=ClinicalTemplate.Profession.choices)
    patient = models.ForeignKey(
        "recordings.Patient",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="reports",
    )
    patient_reference = models.CharField(max_length=120, blank=True)
    sequence = models.PositiveIntegerField(default=1)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.PROCESSING)
    # Registro con los conceptos ya homologados.
    data = models.JSONField(null=True, blank=True)
    # Qué término se reemplazó por qué concepto y dónde (se llena mientras se homologa).
    homologations = models.JSONField(default=list, blank=True)
    # Ids de los temas (``report_topics``) ya validados; con todos puede guardar el informe.
    validated_sections = models.JSONField(default=list, blank=True)
    error = models.CharField(max_length=500, blank=True)
    validated_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"Informe {self.id} ({self.profession} #{self.sequence})"
