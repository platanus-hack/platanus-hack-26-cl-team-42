from django.contrib import admin

from .models import Recording


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
