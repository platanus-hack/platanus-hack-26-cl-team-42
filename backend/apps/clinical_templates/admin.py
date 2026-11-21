from django.contrib import admin

from .models import ClinicalTemplate


@admin.register(ClinicalTemplate)
class ClinicalTemplateAdmin(admin.ModelAdmin):
    """Read-only view: template content is managed in ``data/`` and synced by command."""

    list_display = ("slug", "version", "profession", "name", "is_active", "created_at")
    list_filter = ("profession", "is_active")
    search_fields = ("slug", "name")
    readonly_fields = (
        "slug",
        "name",
        "description",
        "profession",
        "version",
        "output_schema",
        "llm_instructions",
        "content_hash",
        "created_at",
    )
