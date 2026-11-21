"""Versioned clinical templates (JSON Schema) used to structure ICU transcripts.

Each template describes, for one kind of health professional, the structured
record an LLM (Qwen) must produce from the transcript of an audio note taken
during the patient's ICU stay. The JSON Schema content lives in
``apps/clinical_templates/data/`` (source of truth, versioned in git) and is
synced into this table by ``manage.py load_clinical_templates``.

Templates are immutable once stored: a content change creates a new
``version`` and deactivates the previous one, so every extracted record can
keep pointing at the exact schema it was produced with.
"""

from django.db import models
from django.utils.translation import gettext_lazy as _


class ClinicalTemplate(models.Model):
    """A versioned JSON Schema for one health professional's ICU record."""

    class Profession(models.TextChoices):
        MEDICO = "medico", _("Physician")
        ESPECIALISTA = "especialista", _("Specialist")
        ENFERMERIA = "enfermeria", _("Nurse")
        TENS = "tens", _("Nursing technician (TENS)")
        KINESIOLOGIA = "kinesiologia", _("Physiotherapist")

    slug = models.SlugField(max_length=64)
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    profession = models.CharField(max_length=32, choices=Profession.choices)
    version = models.PositiveIntegerField()
    output_schema = models.JSONField()
    llm_instructions = models.TextField()
    content_hash = models.CharField(max_length=64)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["slug", "-version"]
        constraints = [
            models.UniqueConstraint(fields=["slug", "version"], name="unique_template_version"),
        ]

    def __str__(self) -> str:
        return f"{self.slug} v{self.version}"
