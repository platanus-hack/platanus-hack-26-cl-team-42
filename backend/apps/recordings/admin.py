from django.contrib import admin

from .models import Patient, Recording


@admin.register(Recording)
class RecordingAdmin(admin.ModelAdmin):
    list_display = [
        "id",
        "professional",
        "patient_reference",
        "source",
        "duration_seconds",
        "recorded_at",
    ]
    list_filter = ["source"]
    search_fields = ["patient_reference", "professional__email"]
    readonly_fields = ["id", "mime_type", "size_bytes", "created_at"]


@admin.register(Patient)
class PatientAdmin(admin.ModelAdmin):
    list_display = ["name", "identifier", "bed"]
    search_fields = ["name", "identifier"]
    filter_horizontal = ["assigned_to"]
