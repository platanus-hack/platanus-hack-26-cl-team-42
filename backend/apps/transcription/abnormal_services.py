"""Exámenes de laboratorio y escalas fuera de rango de un paciente, ordenados por gravedad.

Las escalas pronósticas (SOFA, APACHE II, SAPS, qSOFA, NEWS) y los exámenes más ligados a
mortalidad (lactato, pH, potasio, troponina…) pesan más. Los umbrales son orientativos y
solo ayudan a priorizar; no reemplazan el juicio clínico.
"""

from collections.abc import Callable
from datetime import datetime
from typing import Any

from pydantic import BaseModel

from apps.recordings.models import Patient

from .evidence_services import _latest_results, canonical_lab
from .homologation_services import normalize
from .models import Evidence

SEVERITY_ORDER = {"critical": 0, "high": 1, "moderate": 2}
SEVERITY_LABELS = {"critical": "Crítico", "high": "Alto", "moderate": "Moderado"}
UPGRADE = {"moderate": "high", "high": "critical", "critical": "critical"}

# Exámenes cuyo desvío se asocia con mortalidad: suben un nivel de gravedad.
MORTALITY_LABS = {
    "lactato",
    "ph",
    "potasio",
    "troponina",
    "creatinina",
    "plaquetas",
    "bilirrubina",
    "inr",
    "procalcitonina",
}


class AbnormalFinding(BaseModel):
    # lab | scale
    kind: str
    name: str
    value: str
    unit: str = ""
    reference: str = ""
    # critical | high | moderate
    severity: str
    severityLabel: str
    # Se asocia con mortalidad (se destaca y se ordena primero).
    mortality: bool = False
    note: str = ""
    at: datetime | None = None


def abnormal_findings(patient: Patient, version_data: dict[str, Any]) -> list[AbnormalFinding]:
    """Escalas y exámenes fuera de rango: lo más grave y ligado a mortalidad primero."""
    found = [*_scale_findings(version_data), *_lab_findings(patient)]
    return sorted(
        found,
        key=lambda f: (SEVERITY_ORDER[f.severity], not f.mortality, f.kind != "scale", f.name),
    )


# --- escalas -----------------------------------------------------------------------------

# (fragmentos del nombre, mortalidad, función puntaje → (gravedad, nota) o None)
ScaleRule = Callable[[float], tuple[str, str] | None]


def _higher_is_worse(moderate: float, high: float, critical: float) -> ScaleRule:
    def rule(score: float) -> tuple[str, str] | None:
        if score >= critical:
            return "critical", "riesgo de mortalidad muy elevado"
        if score >= high:
            return "high", "riesgo de mortalidad elevado"
        if score >= moderate:
            return "moderate", "riesgo de mortalidad aumentado"
        return None

    return rule


def _glasgow(score: float) -> tuple[str, str] | None:
    if score <= 8:
        return "critical", "compromiso grave de conciencia"
    if score <= 12:
        return "high", "compromiso moderado de conciencia"
    if score <= 14:
        return "moderate", "leve compromiso de conciencia"
    return None


def _rass(score: float) -> tuple[str, str] | None:
    if score <= -4:
        return "high", "sedación profunda"
    if score >= 3:
        return "high", "agitación"
    if score <= -3 or score >= 2:
        return "moderate", "fuera del objetivo habitual de sedación"
    return None


def _braden(score: float) -> tuple[str, str] | None:
    if score <= 12:
        return "high", "riesgo alto de lesiones por presión"
    if score <= 14:
        return "moderate", "riesgo moderado de lesiones por presión"
    return None


SCALE_RULES: list[tuple[tuple[str, ...], bool, ScaleRule]] = [
    (("qsofa",), True, _higher_is_worse(1, 2, 3)),
    (("sofa",), True, _higher_is_worse(2, 6, 10)),
    (("apache",), True, _higher_is_worse(10, 15, 25)),
    (("saps",), True, _higher_is_worse(30, 40, 60)),
    (("news",), True, _higher_is_worse(3, 5, 7)),
    (("glasgow", "gcs"), False, _glasgow),
    (("rass",), False, _rass),
    (("braden",), False, _braden),
]


def _scale_findings(data: dict[str, Any]) -> list[AbnormalFinding]:
    found: dict[str, AbnormalFinding] = {}
    for item in data.get("escalas") or []:
        if not isinstance(item, dict):
            continue
        score = item.get("puntaje")
        name = str(item.get("nombre", "")).strip()
        if not isinstance(score, int | float) or isinstance(score, bool) or not name:
            continue
        plain = normalize(name)
        for keys, mortality, rule in SCALE_RULES:
            if not any(key in plain for key in keys):
                continue
            verdict = rule(float(score))
            if verdict:
                severity, note = verdict
                interpretation = str(item.get("interpretacion", "")).strip()
                found[plain] = AbnormalFinding(
                    kind="scale",
                    name=name,
                    value=str(score),
                    severity=severity,
                    severityLabel=SEVERITY_LABELS[severity],
                    mortality=mortality,
                    note=interpretation or note,
                )
            break
    return list(found.values())


# --- laboratorio -------------------------------------------------------------------------


def _lab_findings(patient: Patient) -> list[AbnormalFinding]:
    latest = _latest_results(list(Evidence.objects.filter(patient=patient, kind="lab")))
    found = []
    for code, lab in latest.items():
        if lab.get("flag") not in ("low", "high"):
            continue
        severity = _lab_severity(lab)
        mortality = canonical_lab(code) in MORTALITY_LABS
        if mortality:
            severity = UPGRADE[severity]
        found.append(
            AbnormalFinding(
                kind="lab",
                name=lab["name"],
                value=lab["value"],
                unit=lab.get("unit", ""),
                reference=_reference(lab),
                severity=severity,
                severityLabel=SEVERITY_LABELS[severity],
                mortality=mortality,
                note="por debajo del rango" if lab["flag"] == "low" else "por sobre el rango",
                at=lab["takenAt"],
            )
        )
    return found


def _lab_severity(lab: dict[str, Any]) -> str:
    """Según cuánto se aleja del rango: >100 % crítico, >30 % alto, el resto moderado."""
    numeric, low, high = lab.get("numeric"), lab.get("ref_min"), lab.get("ref_max")
    if numeric is None:
        return "moderate"
    if lab["flag"] == "high" and high:
        deviation = (numeric - high) / abs(high)
    elif lab["flag"] == "low" and low:
        deviation = (low - numeric) / abs(low)
    else:
        return "moderate"
    return "critical" if deviation >= 1.0 else "high" if deviation >= 0.3 else "moderate"


def _reference(lab: dict[str, Any]) -> str:
    low, high = lab.get("ref_min"), lab.get("ref_max")
    if low is not None and high is not None:
        return f"{low:g} a {high:g}"
    if high is not None:
        return f"≤ {high:g}"
    return f"≥ {low:g}" if low is not None else ""
