from django.contrib import admin

from .models import AgentProfile


@admin.register(AgentProfile)
class AgentProfileAdmin(admin.ModelAdmin):
    """Miembros de la clínica sin cuenta que opinan en el consejo de agentes."""

    list_display = ["name", "profession", "is_active"]
    list_filter = ["profession", "is_active"]
    search_fields = ["name", "experience"]
