"""Triage de la bandeja: criticidad, prioridad de visita y tareas pendientes de cada paciente.

Todo sale de la versión oficial vigente del paciente (lo ya consolidado) y de cuándo lo vio por
última vez cualquier profesional. La prioridad de visita crece con la criticidad y con el tiempo
sin visitarlo: un paciente crítico debería verse cada pocas horas; uno estable, un par de veces
por turno.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from django.utils import timezone

from .models import ConsolidatedVersion
from .summary_services import criticality_of

# Cada cuántas horas conviene visitar a un paciente según su criticidad.
VISIT_INTERVAL_HOURS = {"critical": 2.0, "high": 4.0, "moderate": 8.0, "stable": 12.0}
VISIT_NOW_RATIO = 1.0  # pasó el intervalo entero
VISIT_SOON_RATIO = 0.6  # va por más de la mitad
MAX_SCORE = 99.0
# Secciones del registro con tareas por hacer (las metas del día no son tareas).
TASK_SECTIONS = (
    "pendientes",
    "indicaciones",
    "recomendaciones_al_tratante",
    "recomendaciones_equipo",
)
VISIT_LABELS = {
    "now": "Visitar ahora",
    "soon": "Visitar pronto",
    "ok": "Visita al día",
    "unknown": "Sin datos",
}


@dataclass(frozen=True)
class Triage:
    criticality: str  # critical | high | moderate | stable | unknown
    criticality_label: str
    pending_tasks: int
    visit_priority: str  # now | soon | ok | unknown
    visit_priority_label: str
    priority_score: float  # mayor = más urgente de visitar
    hours_since_visit: float | None


def triage_for(
    patient_ids: list[int],
    last_visits: dict[int, datetime | None],
    now: datetime | None = None,
) -> dict[int, Triage]:
    """El triage de cada paciente; sin versión oficial no hay base para clasificarlo."""
    now = now or timezone.now()
    versions = {
        version.patient_id: version
        for version in ConsolidatedVersion.objects.filter(
            patient_id__in=patient_ids, is_current=True
        )
    }
    return {
        patient_id: _triage(versions.get(patient_id), last_visits.get(patient_id), now)
        for patient_id in patient_ids
    }


def _triage(
    version: ConsolidatedVersion | None, last_visit: datetime | None, now: datetime
) -> Triage:
    hours = (now - last_visit).total_seconds() / 3600 if last_visit else None
    if version is None:
        return Triage(
            "unknown", "Sin informe oficial", 0, "unknown", VISIT_LABELS["unknown"], 0.0, hours
        )
    criticality = criticality_of([version.data])
    # Sin ninguna visita registrada, ya pasó todo el intervalo.
    ratio = (
        MAX_SCORE
        if hours is None
        else min(hours / VISIT_INTERVAL_HOURS[criticality.level], MAX_SCORE)
    )
    priority = "now" if ratio >= VISIT_NOW_RATIO else "soon" if ratio >= VISIT_SOON_RATIO else "ok"
    return Triage(
        criticality.level,
        criticality.label,
        _pending_tasks(version.data),
        priority,
        VISIT_LABELS[priority],
        round(ratio, 2),
        hours,
    )


def _pending_tasks(data: dict[str, Any]) -> int:
    return sum(
        1
        for section in TASK_SECTIONS
        for item in (data.get(section) or [])
        if isinstance(item, dict) and item.get("descripcion")
    )
