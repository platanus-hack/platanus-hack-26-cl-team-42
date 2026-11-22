"""Cambios entre informes y su impacto en el registro oficial del paciente.

- ``report_diff``: qué cambió en un informe respecto del informe guardado anterior de la misma
  profesión para el paciente, y qué pasó con cada cambio en la versión oficial (se incorporó,
  el registro mantiene otro valor, quedó en conflicto…). Para un borrador el impacto es una
  previsión: lo que pasaría al guardarlo.
- ``version_changes``: qué cambió en el registro oficial entre una versión y la anterior.

La comparación es semántica: usa los informes ya homologados y la misma identidad de elementos
que la consolidación (``identity_of``), así «norepinefrina» y «noradrenalina» no son un cambio.

Que un elemento no aparezca en el informe nuevo **no** significa que se haya suspendido: el
profesional pudo no mencionarlo. Por eso se informa como «no mencionado» y solo para elementos
de listas (fármacos, dispositivos…); un campo o un texto que falta no se considera un cambio.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal

from django.db.models import Q
from pydantic import BaseModel

from . import consolidation_services
from .consolidation_services import FIELD_LABELS, IDENTITY_KEYS, identity_of, section_title
from .homologation_services import normalize
from .models import ConsolidatedVersion, Reconciliation, Report

ChangeKind = Literal["added", "removed", "changed", "updated"]
# in_record: el registro oficial tiene el valor de este informe.
# official_differs: el registro oficial mantiene otro valor (``officialValue``).
# still_in_record: lo no mencionado sigue vigente en el registro oficial.
# out_of_record: el registro oficial no lo tiene.
# conflict: choca con el registro oficial y espera la reconciliación.
Impact = Literal["in_record", "official_differs", "still_in_record", "out_of_record", "conflict"]

# Controles seriados (uno por hora): solo se compara el último de cada informe.
SERIAL_SECTIONS = frozenset({"control_hemodinamico", "control_respiratorio"})
SKIPPED_FIELDS = frozenset({"evidencia"})
MAX_LABEL = 90


class Change(BaseModel):
    """Un cambio entre dos registros (informes o versiones oficiales)."""

    key: str
    section: str
    sectionTitle: str
    # added: elemento o dato nuevo (sin valor anterior) · removed: no mencionado ·
    # changed: valor distinto · updated: texto distinto.
    kind: ChangeKind
    item: str
    field: str
    before: str
    after: str


class ReportChange(Change):
    impact: Impact | None
    officialValue: str


class ReportRef(BaseModel):
    id: str
    sequence: int
    authorName: str
    recordedAt: datetime


class ReportDiff(BaseModel):
    reportId: str
    # Informe guardado anterior de la misma profesión (``None``: es el primero).
    previous: ReportRef | None
    # Borrador: el impacto es lo que pasaría al guardarlo.
    preview: bool
    # Versión oficial contra la que se mide el impacto (``None``: aún no hay).
    officialVersion: int | None
    changes: list[ReportChange]


def report_diff(viewer, report: Report) -> ReportDiff:
    previous = previous_report(viewer, report)
    changes = diff_data(previous.data if previous else {}, report.data or {})
    official, conflict_keys, preview = _official_reference(report)
    official_facts = _facts(official.data) if official else None
    return ReportDiff(
        reportId=str(report.id),
        previous=_ref(previous) if previous else None,
        preview=preview,
        officialVersion=official.version if official else None,
        changes=[
            _with_impact(change, official_facts, conflict_keys, preview) for change in changes
        ],
    )


def version_changes(
    version: ConsolidatedVersion, previous: ConsolidatedVersion | None
) -> list[Change]:
    """Lo que cambió en el registro oficial al pasar de ``previous`` a ``version``."""
    return diff_data(previous.data, version.data) if previous else []


def previous_report(viewer, report: Report) -> Report | None:
    """El informe guardado anterior de la misma profesión para el paciente, visible al usuario."""
    # Import diferido: report_services importa los servicios de consolidación.
    from .report_services import saved_reports

    candidates = saved_reports(viewer).filter(profession=report.profession).exclude(pk=report.pk)
    if report.patient_id:
        candidates = candidates.filter(patient_id=report.patient_id)
    elif report.patient_reference:
        candidates = candidates.filter(
            patient__isnull=True, patient_reference=report.patient_reference
        )
    else:
        return None
    recorded = "extracted_record__transcription__recording__recorded_at"
    moment = report.extracted_record.transcription.recording.recorded_at
    earlier = Q(**{f"{recorded}__lt": moment}) | Q(**{recorded: moment, "pk__lt": report.pk})
    return candidates.filter(earlier).order_by(f"-{recorded}", "-pk").first()


def diff_data(before: dict[str, Any] | None, after: dict[str, Any] | None) -> list[Change]:
    """Cambios de ``before`` a ``after``, en el orden de las secciones."""
    old, new = _facts(before), _facts(after)
    changes: list[Change] = []
    for key, fact in new.items():
        previous = old.get(key)
        if fact.kind == "item":
            if previous is None:
                changes.append(_change(key, fact, "added", "", fact.value))
        elif previous is None:
            # Un dato que antes no estaba es nuevo; el de un elemento nuevo ya va dentro de él.
            if not (fact.parent and fact.parent not in old):
                changes.append(_change(key, fact, "added", "", fact.value))
        elif _differs(previous.value, fact.value):
            kind: ChangeKind = "updated" if fact.kind == "text" else "changed"
            changes.append(_change(key, fact, kind, previous.value, fact.value))
    for key, fact in old.items():
        if fact.kind == "item" and key not in new:
            changes.append(_change(key, fact, "removed", fact.value, ""))
    order = {section: n for n, section in enumerate([*(after or {}), *(before or {})])}
    return sorted(changes, key=lambda change: order.get(change.section, len(order)))


@dataclass(frozen=True)
class Fact:
    """Un dato comparable de un registro: un elemento de una lista, un campo o un texto."""

    section: str
    kind: Literal["item", "field", "text"]
    item: str
    field: str
    value: str
    # Clave del elemento al que pertenece el campo (si es de un elemento de lista).
    parent: str = ""


def _facts(data: dict[str, Any] | None) -> dict[str, Fact]:
    facts: dict[str, Fact] = {}
    for section, value in (data or {}).items():
        if section in consolidation_services.SKIPPED_SECTIONS or _empty(value):
            continue
        if isinstance(value, list) and section in SERIAL_SECTIONS:
            last = [item for item in value if isinstance(item, dict)][-1:]
            for item in last:
                for path, shown in _fields(item):
                    facts[f"{section}:ultimo:{path}"] = Fact(
                        section, "field", "Último control", _field_label(path), shown
                    )
        elif isinstance(value, list):
            for item in value:
                facts.update(_item_facts(section, item))
        elif isinstance(value, dict):
            for path, shown in _fields(value):
                facts[f"{section}::{path}"] = Fact(section, "field", "", _field_label(path), shown)
        else:
            facts[section] = Fact(section, "text", "", "", str(value))
    return facts


def _item_facts(section: str, item: Any) -> dict[str, Fact]:
    if _empty(item):
        return {}
    identity = identity_of(item)
    if not identity:
        text = _text_of(item)
        return {f"{section}#{normalize(text)}": Fact(section, "item", _short(text), "", text)}
    id_key = next(key for key in IDENTITY_KEYS if identity_of({key: item.get(key)}) == identity)
    label = _short(str(item[id_key]))
    key = f"{section}:{identity}"
    fields = _fields(item, skip={id_key})
    # El elemento completo, empezando por lo que lo identifica: «Meropenem · 1 g · EV».
    text = " · ".join([str(item[id_key]), *(shown for _, shown in fields)])
    facts = {key: Fact(section, "item", label, "", text)}
    for path, shown in fields:
        facts[f"{key}:{path}"] = Fact(section, "field", label, _field_label(path), shown, key)
    return facts


def _fields(
    value: dict[str, Any], skip: set[str] | None = None, prefix: str = ""
) -> list[tuple[str, str]]:
    """Campos con contenido de un elemento, como ``(ruta, valor a mostrar)``."""
    skipped = SKIPPED_FIELDS | (skip or set())
    if "dosis" in value:
        skipped = skipped | {"unidad"}  # la unidad va junto a la dosis
    found: list[tuple[str, str]] = []
    for key, field_value in value.items():
        if key in skipped or _empty(field_value):
            continue
        path = f"{prefix}{key}"
        if isinstance(field_value, dict):
            found += _fields(field_value, prefix=f"{path}.")
        elif key == "dosis" and value.get("unidad"):
            found.append((path, f"{_scalar(field_value)} {value['unidad']}"))
        else:
            found.append((path, _text_of(field_value)))
    return found


def _text_of(value: Any) -> str:
    if isinstance(value, dict):
        return " · ".join(
            _text_of(v) for k, v in value.items() if k not in SKIPPED_FIELDS and not _empty(v)
        )
    if isinstance(value, list):
        return ", ".join(_text_of(v) for v in value if not _empty(v))
    return _scalar(value)


def _scalar(value: Any) -> str:
    if isinstance(value, bool):
        return "sí" if value else "no"
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value)


def _empty(value: Any) -> bool:
    return value in (None, "", [], {})


def _differs(old: str, new: str) -> bool:
    return normalize(old) != normalize(new)


def _short(text: str) -> str:
    return text if len(text) <= MAX_LABEL else text[: MAX_LABEL - 1].rstrip() + "…"


def _field_label(path: str) -> str:
    return " · ".join(FIELD_LABELS.get(part, part.replace("_", " ")) for part in path.split("."))


def _change(key: str, fact: Fact, kind: ChangeKind, before: str, after: str) -> Change:
    return Change(
        key=key,
        section=fact.section,
        sectionTitle=section_title(fact.section),
        kind=kind,
        item=fact.item,
        field=fact.field,
        before=before,
        after=after,
    )


def _official_reference(report: Report) -> tuple[ConsolidatedVersion | None, set[str], bool]:
    """Versión oficial con que se mide el impacto, claves de los conflictos y si es previsión."""
    if report.patient_id is None:
        return None, set(), False
    current = consolidation_services.current_version(report.patient)
    if report.status != Report.Status.DONE:
        if current is None:
            return None, set(), True
        found = consolidation_services.detect_conflicts(current, report)
        return current, {candidate["key"] for candidate in found}, True
    if report.consolidation == Report.Consolidation.RECONCILING:
        open_keys = set(
            report.reconciliations.filter(status=Reconciliation.Status.OPEN)
            .filter(conflicts__status="open")
            .values_list("conflicts__key", flat=True)
        )
        return current, open_keys, False
    if report.consolidation == Report.Consolidation.CONSOLIDATED:
        resolved = report.reconciliations.filter(result_version__isnull=False).first()
        return (resolved.result_version if resolved else current), set(), False
    return report.versions.order_by("-version").first() or current, set(), False


def _with_impact(
    change: Change, official: dict[str, Fact] | None, conflict_keys: set[str], preview: bool
) -> ReportChange:
    impact, official_value = _impact(change, official, conflict_keys, preview)
    return ReportChange(**change.model_dump(), impact=impact, officialValue=official_value)


def _impact(
    change: Change, official: dict[str, Fact] | None, conflict_keys: set[str], preview: bool
) -> tuple[Impact | None, str]:
    if official is None:
        # Un borrador sin versión oficial se convertirá en ella al guardarse.
        return ("in_record", "") if preview and change.kind != "removed" else (None, "")
    if _in_conflict(change, conflict_keys):
        return "conflict", ""
    fact = official.get(change.key)
    if change.kind == "removed":
        return ("still_in_record", fact.value) if fact else ("out_of_record", "")
    if fact is None:
        # Al guardarse, lo nuevo se suma a la versión oficial (la consolidación completa huecos).
        return ("in_record", "") if preview else ("out_of_record", "")
    if fact.kind == "item" or not _differs(fact.value, change.after):
        return "in_record", ""
    # Ante diferencias que no son conflicto, la consolidación conserva lo ya oficial.
    return "official_differs", fact.value


def _in_conflict(change: Change, conflict_keys: set[str]) -> bool:
    if change.key in conflict_keys:
        return True
    # Choques de alergia: «alergia:<alérgeno>:<sección del fármaco>:<fármaco>».
    section_key, _, identity = change.key.partition(":")
    if change.kind != "added" or not identity or ":" in identity:
        return False
    return any(
        key.startswith("alergia:")
        and (key.endswith(f":{section_key}:{identity}") or key.startswith(f"alergia:{identity}:"))
        for key in conflict_keys
    )


def _ref(report: Report) -> ReportRef:
    return ReportRef(
        id=str(report.id),
        sequence=report.sequence,
        authorName=report.author.name or report.author.email,
        recordedAt=report.extracted_record.transcription.recording.recorded_at,
    )
