from django.contrib import admin

from .models import LogRecord


@admin.register(LogRecord)
class LogRecordAdmin(admin.ModelAdmin):
    list_display = ("id", "kind", "name", "created_at")
    list_filter = ("kind", "name")
    search_fields = ("name",)
    readonly_fields = ("kind", "name", "payload", "created_at")
