"""Tendencias de exámenes y escalas de un paciente, para orientar el juicio clínico.

Cada serie junta los valores en el tiempo (exámenes cargados como evidencia y escalas de los
informes guardados) y dice si el paciente va mejorando, empeorando o se mantiene. Es una ayuda
para mirar la evolución, no un diagnóstico.
"""

from datetime import datetime
from typing import Any

from pydantic import BaseModel

from apps.recordings.models import Patient

from .abnormal_services import MORTALITY_LABS
from .evidence_services import canonical_lab
from .homologation_services import normalize
from .models import Evidence
from .report_services import saved_reports

MAX_SERIES = 8
FLAT = 0.05  # cambio relativo bajo el cual la serie se considera estable

# Escalas: True si un puntaje mayor es peor, False si uno menor es peor, None si no hay sentido.
SCALE_WORSE_WHEN_HIGHER: dict[str, bool | None] = {
    "sofa": True,
    "apache": True,
    "saps": True,
    "news": True,
    "glasgow": False,
    "gcs": False,
    "braden": False,
    "rass": None,
}
MORTALITY_SCALES = ("sofa", "apache", "saps", "news")


class TrendPoint(BaseModel):
    at: datetime
    value: float


class Trend(BaseModel):
    # lab | scale
    kind: str
    name: str
    unit: str = ""
    refMin: float | None = None
    refMax: float | None = None
    mortality: bool = False
    # worsening | improving | stable | neutral
    status: str
    # Último valor menos el primero.
    change: float
    points: list[TrendPoint]


def patient_trends(professional, patient: Patient) -> list[Trend]:
    """Series con al menos dos mediciones: las que empeoran y las ligadas a mortalidad primero."""
    series = [*_lab_trends(patient), *_scale_trends(professional, patient)]
    order = {"worsening": 0, "stable": 2, "improving": 1, "neutral": 3}
    series.sort(key=lambda t: (order[t.status], not t.mortality, t.kind != "scale", t.name))
    return series[:MAX_SERIES]


def _lab_trends(patient: Patient) -> list[Trend]:
    grouped: dict[str, dict[str, Any]] = {}
    for item in Evidence.objects.filter(patient=patient, kind="lab").order_by("taken_at"):
        for result in item.results:
            if result.get("numeric") is None:
                continue
            code = canonical_lab(result["name"])
            entry = grouped.setdefault(code, {"result": result, "points": []})
            entry["result"] = result
            entry["points"].append(TrendPoint(at=item.taken_at, value=float(result["numeric"])))
    trends = []
    for code, entry in grouped.items():
        points, result = entry["points"], entry["result"]
        if len(points) < 2:
            continue
        low, high = result.get("ref_min"), result.get("ref_max")
        mortality = code in MORTALITY_LABS
        outside = any(_deviation(p.value, low, high) > 0 for p in points)
        if not (outside or mortality):
            continue
        trends.append(
            Trend(
                kind="lab",
                name=result["name"],
                unit=result.get("unit", ""),
                refMin=low,
                refMax=high,
                mortality=mortality,
                status=_lab_status(points, low, high),
                change=round(points[-1].value - points[0].value, 2),
                points=points,
            )
        )
    return trends


def _deviation(value: float, low: float | None, high: float | None) -> float:
    """Cuánto se aleja del rango, en fracción del límite (0 si está dentro)."""
    if high is not None and value > high:
        return (value - high) / abs(high or 1)
    if low is not None and value < low:
        return (low - value) / abs(low or 1)
    return 0.0


def _lab_status(points: list[TrendPoint], low: float | None, high: float | None) -> str:
    first, last = _deviation(points[0].value, low, high), _deviation(points[-1].value, low, high)
    if first == 0 and last == 0:
        return "stable"
    if abs(last - first) <= FLAT:
        return "stable"
    return "worsening" if last > first else "improving"


def _scale_trends(professional, patient: Patient) -> list[Trend]:
    grouped: dict[str, dict[str, Any]] = {}
    reports = saved_reports(professional).filter(patient=patient)
    for report in reports.order_by("extracted_record__transcription__recording__recorded_at"):
        moment = report.extracted_record.transcription.recording.recorded_at
        for item in (report.data or {}).get("escalas") or []:
            score = item.get("puntaje") if isinstance(item, dict) else None
            name = str(item.get("nombre", "")).strip() if isinstance(item, dict) else ""
            if not name or not isinstance(score, int | float) or isinstance(score, bool):
                continue
            entry = grouped.setdefault(normalize(name), {"name": name, "points": []})
            entry["points"].append(TrendPoint(at=moment, value=float(score)))
    trends = []
    for plain, entry in grouped.items():
        points = entry["points"]
        if len(points) < 2:
            continue
        key = next((k for k in SCALE_WORSE_WHEN_HIGHER if k in plain), None)
        worse_high = SCALE_WORSE_WHEN_HIGHER.get(key) if key else None
        trends.append(
            Trend(
                kind="scale",
                name=entry["name"],
                mortality=key in MORTALITY_SCALES,
                status=_scale_status(points, worse_high),
                change=round(points[-1].value - points[0].value, 2),
                points=points,
            )
        )
    return trends


def _scale_status(points: list[TrendPoint], worse_when_higher: bool | None) -> str:
    delta = points[-1].value - points[0].value
    if worse_when_higher is None:
        return "neutral"
    base = max(abs(points[0].value), 1.0)
    if abs(delta) / base <= FLAT:
        return "stable"
    return "worsening" if (delta > 0) == worse_when_higher else "improving"
