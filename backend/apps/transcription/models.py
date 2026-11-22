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

    class Consolidation(models.TextChoices):
        PENDING = "pending", _("Not consolidated")
        # Primer informe guardado del paciente: es la versión oficial.
        OFFICIAL = "official", _("Official")
        # Coincidía con la versión oficial: se incorporó sin conflictos.
        MERGED = "merged", _("Merged")
        # Chocaba con lo ya reportado: espera la reconciliación entre los profesionales.
        RECONCILING = "reconciling", _("In reconciliation")
        # Sus conflictos se resolvieron y quedó incorporado a la versión oficial.
        CONSOLIDATED = "consolidated", _("Consolidated")

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
    # Ids de las aclaraciones ya revisadas por el autor (``review_services``). En informes
    # antiguos guardaba ids de temas validados, que hoy se ignoran.
    validated_sections = models.JSONField(default=list, blank=True)
    # Contradicciones con la evidencia (exámenes) detectadas al registrar el informe; el autor
    # las ve en la validación. Cada una: {id, severity, kind, section, topic, message, ...}.
    evidence_alerts = models.JSONField(default=list, blank=True)
    error = models.CharField(max_length=500, blank=True)
    # Qué pasó con el informe al guardarse respecto de la versión oficial del paciente.
    consolidation = models.CharField(
        max_length=14, choices=Consolidation.choices, default=Consolidation.PENDING
    )
    validated_at = models.DateTimeField(null=True, blank=True)
    # Cuándo su autor confirmó haberlo pasado a la ficha institucional (``None`` = por pasar).
    charted_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"Informe {self.id} ({self.profession} #{self.sequence})"


class ConsolidatedVersion(models.Model):
    """Versión consolidada («oficial») del estado de un paciente; las anteriores se conservan."""

    class Reason(models.TextChoices):
        OFFICIAL = "official", _("First saved report")
        MERGE = "merge", _("Report without conflicts")
        RECONCILIATION = "reconciliation", _("Conflicts resolved")

    patient = models.ForeignKey(
        "recordings.Patient", on_delete=models.PROTECT, related_name="versions"
    )
    version = models.PositiveIntegerField()
    data = models.JSONField()
    # Qué informe aportó cada sección y elemento: ``{"<sección>::<identidad>": <id de informe>}``.
    provenance = models.JSONField(default=dict, blank=True)
    reason = models.CharField(max_length=14, choices=Reason.choices)
    source_report = models.ForeignKey(
        Report, on_delete=models.SET_NULL, null=True, blank=True, related_name="versions"
    )
    is_current = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-version"]
        constraints = [
            models.UniqueConstraint(fields=["patient", "version"], name="unique_patient_version"),
        ]

    def __str__(self) -> str:
        return f"Versión {self.version} de {self.patient_id}"


class Reconciliation(models.Model):
    """Revisión de un informe guardado que chocó con la versión oficial del paciente."""

    class Status(models.TextChoices):
        OPEN = "open", _("Open")
        RESOLVED = "resolved", _("Resolved")

    patient = models.ForeignKey(
        "recordings.Patient", on_delete=models.PROTECT, related_name="reconciliations"
    )
    report = models.ForeignKey(Report, on_delete=models.CASCADE, related_name="reconciliations")
    base_version = models.ForeignKey(
        ConsolidatedVersion, on_delete=models.PROTECT, related_name="reconciliations"
    )
    result_version = models.ForeignKey(
        ConsolidatedVersion,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="resolved_reconciliations",
    )
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.OPEN)
    created_at = models.DateTimeField(auto_now_add=True)
    resolved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]


class Conflict(models.Model):
    """Un choque entre lo reportado por dos informes sobre el mismo dato."""

    class Status(models.TextChoices):
        OPEN = "open", _("Open")
        RESOLVED = "resolved", _("Resolved")

    reconciliation = models.ForeignKey(
        Reconciliation, on_delete=models.CASCADE, related_name="conflicts"
    )
    key = models.CharField(max_length=200)
    kind = models.CharField(max_length=20)
    section = models.CharField(max_length=80)
    label = models.CharField(max_length=300)
    # Cada lado: {reportId, authorId, authorName, profession, value, evidence, patch}.
    side_a = models.JSONField()
    side_b = models.JSONField()
    explanation = models.TextField(blank=True)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.OPEN)
    # {mode: accepted|consensus|off_shift|sole, side: a|b|custom, value, decidedBy, decidedAt}
    resolution = models.JSONField(null=True, blank=True)
    # {by, side: a|b|custom, value}: propuesta que la otra parte debe aceptar (consenso).
    proposal = models.JSONField(null=True, blank=True)
    # Orientación del agente (se genera sola al abrirse el conflicto): qué postura parece más
    # segura y qué profesional adicional conviene consultar.
    guidance = models.JSONField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["id"]


class ConflictNote(models.Model):
    """Nota de un profesional en la conversación del conflicto: deja registro de sus razones."""

    class Kind(models.TextChoices):
        NOTE = "note", _("Note")
        EXTERNAL = "external", _("External opinion")
        SYSTEM = "system", _("System")

    conflict = models.ForeignKey(Conflict, on_delete=models.CASCADE, related_name="notes")
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True, related_name="+"
    )
    kind = models.CharField(max_length=10, choices=Kind.choices, default=Kind.NOTE)
    body = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at", "id"]


class ExternalConsult(models.Model):
    """Opinión externa pedida a otro profesional, con el caso anonimizado."""

    class Status(models.TextChoices):
        REQUESTED = "requested", _("Requested")
        ANSWERED = "answered", _("Answered")

    conflict = models.ForeignKey(Conflict, on_delete=models.CASCADE, related_name="consults")
    requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+"
    )
    consultant = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="external_consults"
    )
    # Resumen sin nombre, identificador ni cama del paciente, ni nombres de los profesionales.
    brief = models.TextField()
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.REQUESTED)
    reply = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    answered_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]


class PendingClosure(models.Model):
    """Un pendiente de un informe que alguien del equipo dio por cerrado."""

    patient = models.ForeignKey(
        "recordings.Patient", on_delete=models.CASCADE, related_name="pending_closures"
    )
    # «pend-<id de informe>-<posición>»: identifica el pendiente dentro del registro clínico.
    pending_id = models.CharField(max_length=80, unique=True)
    closed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+"
    )
    closed_at = models.DateTimeField(auto_now_add=True)


class Handoff(models.Model):
    """Traspaso de pacientes de un profesional a otro, con una copia fija de lo comunicado."""

    from_user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="handoffs_sent"
    )
    to_user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="handoffs_received"
    )
    note = models.CharField(max_length=1000, blank=True)
    # Una copia por paciente, tal como se vio al enviar (no cambia aunque el registro cambie).
    snapshots = models.JSONField()
    sent_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-sent_at"]


class Evidence(models.Model):
    """Evidencia clínica de un paciente además de los dictados: exámenes, imágenes, cultivos…"""

    class Kind(models.TextChoices):
        LAB = "lab", _("Laboratory")
        IMAGING = "imaging", _("Imaging")
        CULTURE = "culture", _("Culture")
        OTHER = "other", _("Other")

    patient = models.ForeignKey(
        "recordings.Patient", on_delete=models.CASCADE, related_name="evidence"
    )
    kind = models.CharField(max_length=10, choices=Kind.choices, default=Kind.LAB)
    title = models.CharField(max_length=200)
    # Cuándo se tomó la muestra o se hizo el examen (no cuándo se cargó).
    taken_at = models.DateTimeField()
    # Resultados medidos: [{name, value, unit, numeric, ref_min, ref_max, flag}].
    results = models.JSONField(default=list, blank=True)
    # Informe en texto (p. ej. de una imagen o de un cultivo).
    findings = models.TextField(blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-taken_at", "-id"]
