"""Revisión por excepción de un informe: solo lo que exige una decisión de su autor.

Antes de guardar un informe, su autor revisa únicamente los *puntos pendientes*:

- **Conflictos con la evidencia** (``evidence``): las alertas de ``evidence_services`` sin dar
  por revisadas. Severidad ``high`` (rojo: el examen está fuera de rango y el informe lo
  contradice) o ``medium`` (ámbar: discrepancias rutinarias).
- **Aclaraciones** (``clarification``, siempre ámbar): algo dictado de forma explícita que,
  por un dato que falta, queda difícil de interpretar o de ejecutar. Las reglas son pocas y
  estrechas, sobre la estructura del registro (nunca sobre texto libre):

  * un medicamento o una droga en infusión con dosis numérica pero sin unidad;
  * un medicamento *indicado* o *modificado* sin dosis;
  * un antimicrobiano que se inicia, ajusta, escala o desescala sin dosis.

  Un campo vacío por sí solo **no** es un pendiente: la mayoría de los vacíos son cosas que
  simplemente no se dictaron. Limitación conocida: no se detectan ambigüedades en texto libre
  (p. ej. «subir la noradrenalina» sin decir a cuánto dentro de un resumen).

Las alertas de evidencia se dan por revisadas en la propia alerta (``acknowledged``, no se
borra). Las aclaraciones revisadas se guardan por id en ``Report.validated_sections`` (antes
guardaba los temas validados; esos ids antiguos se ignoran). Al completar una sección, sus
aclaraciones vuelven a quedar pendientes.
"""

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel

from .evidence_services import canonical_lab
from .models import Evidence, Report

CLARIFICATION_PREFIX = "clarification:"
SEVERITY_ORDER = {"high": 0, "medium": 1}
KIND_ORDER = {"evidence": 0, "clarification": 1}
# Acciones sobre un antimicrobiano que no se pueden ejecutar sin dosis.
ACTIONS_NEEDING_DOSE = {
    "inicio": "se inicia",
    "ajuste": "se ajusta",
    "escalamiento": "se escala",
    "desescalamiento": "se desescala",
}


class ReviewItem(BaseModel):
    id: str
    kind: Literal["evidence", "clarification"]
    severity: Literal["high", "medium"]
    section: str
    message: str
    # Posición del ítem dictado dentro de la sección (si es una lista), para mostrarlo.
    itemIndex: int | None = None
    # Solo en conflictos con la evidencia: tipo de alerta y examen de origen.
    alertKind: str | None = None
    evidenceId: int | None = None
    evidenceTitle: str = ""
    evidenceTakenAt: datetime | None = None
    fromEarlierVersion: bool = False
    reviewed: bool


class ReviewError(ValueError):
    """El punto no existe en el informe."""


def review_items(report: Report) -> list[ReviewItem]:
    """Los puntos a revisar del informe: primero los graves, luego en el orden del informe."""
    data = report.data or {}
    reviewed = set(report.validated_sections or [])
    items = [*_evidence_items(report), *_clarification_items(data, reviewed)]
    sections = list(data)

    def position(item: ReviewItem) -> tuple[int, int, int]:
        section = sections.index(item.section) if item.section in sections else len(sections)
        return (SEVERITY_ORDER[item.severity], KIND_ORDER[item.kind], section)

    return sorted(items, key=position)


def pending_items(report: Report) -> list[ReviewItem]:
    return [item for item in review_items(report) if not item.reviewed]


def report_evidence_alerts(report: Report) -> list[dict[str, Any]]:
    """Excluye omisiones antiguas que apuntan a secciones ajenas al informe."""
    data = report.data or {}
    return [
        alert
        for alert in (report.evidence_alerts or [])
        if alert.get("kind") != "omission" or alert["section"] in data
    ]


def mark_reviewed(report: Report, item_id: str) -> None:
    """Da por revisado un punto: la alerta queda marcada, la aclaración queda registrada."""
    if item_id.startswith(CLARIFICATION_PREFIX):
        if item_id not in {c["id"] for c in clarifications(report.data or {})}:
            raise ReviewError("No existe ese punto por revisar.")
        if item_id not in report.validated_sections:
            report.validated_sections = [*report.validated_sections, item_id]
        report.save(update_fields=["validated_sections", "updated_at"])
        return
    found = False
    for alert in report.evidence_alerts:
        if alert["id"] == item_id:
            alert["acknowledged"] = True
            found = True
    if not found:
        raise ReviewError("No existe ese punto por revisar.")
    report.save(update_fields=["evidence_alerts", "updated_at"])


def reviewed_after_change(
    reviewed: list[str], changed_section: str | None, item_index: int | None = None
) -> list[str]:
    """Las aclaraciones revisadas que siguen valiendo tras rehacer el informe.

    Las de la sección completada vuelven a quedar pendientes; los ids antiguos (temas) se
    descartan.
    """
    changed = f"{CLARIFICATION_PREFIX}{changed_section}:" if changed_section else None
    if changed and item_index is not None:
        changed = f"{changed}{item_index}:"
    return [
        key
        for key in reviewed
        if key.startswith(CLARIFICATION_PREFIX) and not (changed and key.startswith(changed))
    ]


def clarifications(data: dict[str, Any]) -> list[dict[str, Any]]:
    """Aclaraciones del registro: ``{id, section, index, message}`` (reglas estrechas)."""
    found: list[dict[str, Any]] = []

    def add(section: str, index: int, rule: str, message: str) -> None:
        found.append(
            {
                "id": f"{CLARIFICATION_PREFIX}{section}:{index}:{rule}",
                "section": section,
                "index": index,
                "message": message,
            }
        )

    for index, item in _items(data, "medicamentos"):
        name = _text(item.get("nombre")) or _text(item.get("principio_activo"))
        action = item.get("accion")
        if not name or action in ("suspendido", "omitido"):
            continue
        if _is_number(item.get("dosis")) and not _text(item.get("unidad")):
            add(
                "medicamentos",
                index,
                "unidad",
                f"{name}: se dictó la dosis {item['dosis']:g} sin unidad (mg, g, UI…).",
            )
        elif item.get("dosis") is None and action in ("indicado", "modificado"):
            add("medicamentos", index, "dosis", f"{name}: quedó {action} sin dosis.")

    for index, item in _items(data, "drogas_infusion"):
        name = _text(item.get("farmaco"))
        if not name or item.get("tendencia") == "suspension":
            continue
        if _is_number(item.get("dosis")) and not _text(item.get("unidad")):
            add(
                "drogas_infusion",
                index,
                "unidad",
                f"{name}: se dictó la dosis {item['dosis']:g} sin unidad (mcg/kg/min, ml/h…).",
            )

    for index, item in _items(data, "antimicrobianos"):
        name = _text(item.get("farmaco"))
        action = item.get("accion")
        if name and action in ACTIONS_NEEDING_DOSE and not _text(item.get("dosis")):
            add(
                "antimicrobianos",
                index,
                "dosis",
                f"{name}: {ACTIONS_NEEDING_DOSE[action]} sin dosis.",
            )
    return found


def _evidence_items(report: Report) -> list[ReviewItem]:
    alerts = report_evidence_alerts(report)
    ids = {a.get("evidenceId") for a in alerts if a.get("evidenceId")}
    sources = {e.id: e for e in Evidence.objects.filter(pk__in=ids)} if ids else {}
    data = report.data or {}
    items = []
    for alert in alerts:
        source = sources.get(alert.get("evidenceId"))
        items.append(
            ReviewItem(
                id=alert["id"],
                kind="evidence",
                severity="high" if alert.get("severity") == "high" else "medium",
                section=alert["section"],
                message=alert["message"],
                itemIndex=_alert_index(alert, data),
                alertKind=alert.get("kind"),
                evidenceId=source.id if source else None,
                evidenceTitle=source.title if source else "",
                evidenceTakenAt=source.taken_at if source else None,
                fromEarlierVersion=bool(alert.get("fromEarlierVersion")),
                reviewed=bool(alert.get("acknowledged")),
            )
        )
    return items


def _alert_index(alert: dict[str, Any], data: dict[str, Any]) -> int | None:
    """El examen dictado al que se refiere una alerta de valor (``value:<sección>:<examen>``)."""
    if alert.get("kind") != "value":
        return None
    code = str(alert["id"]).rsplit(":", 1)[-1]
    for index, item in _items(data, alert["section"]):
        if item.get("examen") and canonical_lab(str(item["examen"])) == code:
            return index
        if alert["section"] == "control_hemodinamico" and item.get("lactato") is not None:
            return index
    return None


def _clarification_items(data: dict[str, Any], reviewed: set[str]) -> list[ReviewItem]:
    return [
        ReviewItem(
            id=c["id"],
            kind="clarification",
            severity="medium",
            section=c["section"],
            message=c["message"],
            itemIndex=c["index"],
            reviewed=c["id"] in reviewed,
        )
        for c in clarifications(data)
    ]


def _items(data: dict[str, Any], section: str):
    value = data.get(section)
    if not isinstance(value, list):
        return []
    return [(index, item) for index, item in enumerate(value) if isinstance(item, dict)]


def _text(value: Any) -> str:
    return str(value).strip() if value not in (None, "") else ""


def _is_number(value: Any) -> bool:
    return isinstance(value, int | float) and not isinstance(value, bool)
