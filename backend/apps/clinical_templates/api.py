"""Django Ninja API for ICU clinical templates.

Mounted at ``/clinical-templates`` on the shared Ninja API (see
``conf/urls.py``), so full paths are ``/-/api/clinical-templates/`` etc.
"""

from __future__ import annotations

from typing import Any

from django.shortcuts import get_object_or_404
from ninja import Body, ModelSchema, Router, Schema

from . import services
from .models import ClinicalTemplate

router = Router(tags=["clinical templates"])

# =============================================================================
# Schemas
# =============================================================================


class TemplateSummaryOut(ModelSchema):
    class Meta:
        model = ClinicalTemplate
        fields = ["slug", "name", "description", "profession", "version", "created_at"]


class TemplateDetailOut(ModelSchema):
    class Meta:
        model = ClinicalTemplate
        fields = [
            "slug",
            "name",
            "description",
            "profession",
            "version",
            "output_schema",
            "llm_instructions",
            "created_at",
        ]


class ValidationIssueOut(Schema):
    path: str
    message: str


class ValidationOut(Schema):
    valid: bool
    template_slug: str
    template_version: int
    errors: list[ValidationIssueOut]


# =============================================================================
# Endpoints
# =============================================================================


@router.get("/", response=list[TemplateSummaryOut])
def list_templates(request):
    """Active clinical templates, one per professional type."""
    return ClinicalTemplate.objects.filter(is_active=True)


@router.get("/{slug}", response=TemplateDetailOut)
def get_template(request, slug: str, version: int | None = None):
    """A template's JSON Schema and LLM instructions (active version by default)."""
    if version is None:
        return get_object_or_404(ClinicalTemplate, slug=slug, is_active=True)
    return get_object_or_404(ClinicalTemplate, slug=slug, version=version)


@router.post("/{slug}/validate", response=ValidationOut)
def validate_record(request, slug: str, payload: dict[str, Any] = Body(...)):
    """Validate an extracted record (e.g. Qwen's output) against the active template."""
    template = get_object_or_404(ClinicalTemplate, slug=slug, is_active=True)
    issues = services.validate_record(template, payload)
    return ValidationOut(
        valid=not issues,
        template_slug=template.slug,
        template_version=template.version,
        errors=[ValidationIssueOut(**issue.model_dump()) for issue in issues],
    )
