"""Consolidación: del informe guardado a la versión oficial del paciente.

- El primer informe guardado de un paciente es su versión oficial (v1).
- Cada informe guardado después se compara con la versión oficial vigente. Si no choca con
  nada, se incorpora y nace una versión nueva. Si choca (mismo dato, valores distintos, o una
  indicación que contradice una alergia), se abre una reconciliación entre los profesionales
  implicados y la versión oficial no cambia hasta resolver todos los choques.
- Las versiones anteriores nunca se borran.

La comparación usa los informes ya homologados: «norepinefrina» y «noradrenalina» son el
mismo fármaco, por eso la homologación va antes.
"""

import copy
import json
import logging
from typing import Any

from django.db import transaction
from django.utils import timezone

from .homologation_services import normalize
from .models import ConsolidatedVersion, Report

logger = logging.getLogger(__name__)

IDENTITY_KEYS = (
    "farmaco",
    "nombre",
    "tipo",
    "agente",
    "parametro",
    "examen",
    "muestra",
    "descripcion",
    "objetivo",
    "hora",
)
# sección -> (campo que identifica al elemento, campos que se comparan entre informes)
COMPARABLE: dict[str, tuple[str, tuple[str, ...]]] = {
    "drogas_infusion": ("farmaco", ("dosis",)),
    "medicamentos": ("nombre", ("dosis", "via", "frecuencia")),
    "antimicrobianos": ("farmaco", ("dosis",)),
    "dispositivos_invasivos": ("tipo", ("ubicacion",)),
    "escalas": ("nombre", ("puntaje",)),
    "alergias": ("agente", ("reaccion",)),
}
FIELD_LABELS = {
    "dosis": "dosis",
    "via": "vía",
    "frecuencia": "frecuencia",
    "ubicacion": "ubicación",
    "puntaje": "puntaje",
    "reaccion": "reacción",
}
# alérgeno -> términos de fármacos del mismo grupo (todo sin tildes ni mayúsculas)
ALLERGEN_GROUPS: dict[str, tuple[str, ...]] = {
    "penicilina": (
        "penicilina",
        "amoxicilina",
        "ampicilina",
        "piperacilina",
        "cloxacilina",
        "tazobactam",
    ),
}
DRUG_SECTIONS = (
    ("medicamentos", "nombre"),
    ("drogas_infusion", "farmaco"),
    ("antimicrobianos", "farmaco"),
)
RELATIVE_TOLERANCE = 0.05
SKIPPED_SECTIONS = frozenset({"metadatos"})

Patch = dict[str, Any]


def consolidate(report: Report) -> Report:
    """Incorpora un informe recién guardado a la versión oficial de su paciente."""
    # Import diferido: reconciliation_services importa este módulo.
    from . import reconciliation_services

    patient = report.patient
    if patient is None:
        return report  # sin paciente no hay versión oficial a la que sumarse

    with transaction.atomic():
        current = current_version(patient)
        if current is None:
            create_version(
                patient, report.data or {}, {}, report, ConsolidatedVersion.Reason.OFFICIAL
            )
            _set(report, Report.Consolidation.OFFICIAL)
            return report
        candidates = detect_conflicts(current, report)
        if not candidates:
            data, provenance = merge_data(current, report)
            create_version(patient, data, provenance, report, ConsolidatedVersion.Reason.MERGE)
            _set(report, Report.Consolidation.MERGED)
            return report
        reconciliation_services.open_reconciliation(report, current, candidates)
        _set(report, Report.Consolidation.RECONCILING)
        return report


def current_version(patient) -> ConsolidatedVersion | None:
    return ConsolidatedVersion.objects.filter(patient=patient, is_current=True).first()


def create_version(
    patient, data: dict[str, Any], provenance: dict[str, int], source: Report | None, reason: str
) -> ConsolidatedVersion:
    previous = ConsolidatedVersion.objects.filter(patient=patient).order_by("-version").first()
    ConsolidatedVersion.objects.filter(patient=patient, is_current=True).update(is_current=False)
    return ConsolidatedVersion.objects.create(
        patient=patient,
        version=(previous.version + 1) if previous else 1,
        data=data,
        provenance=provenance or _provenance_of(data, source),
        reason=reason,
        source_report=source,
    )


def detect_conflicts(base: ConsolidatedVersion, report: Report) -> list[dict[str, Any]]:
    """Choques entre la versión oficial y un informe nuevo (cada uno con sus dos lados)."""
    new_data = report.data or {}
    sources = _source_reports(base)
    found: list[dict[str, Any]] = []

    for section, (id_key, fields) in COMPARABLE.items():
        base_items = {identity_of(i): i for i in _items(base.data, section) if identity_of(i)}
        for item in _items(new_data, section):
            identity = identity_of(item)
            old = base_items.get(identity) if identity else None
            if old is None:
                continue
            for field in fields:
                if _differs(old.get(field), item.get(field)):
                    source = sources.get(base.provenance.get(f"{section}::{identity}"))
                    found.append(
                        _value_conflict(section, id_key, identity, field, old, item, source, report)
                    )
    found.extend(_allergy_conflicts(base, sources, report))
    return found


def merge_data(
    base: ConsolidatedVersion, report: Report, patches: list[Patch] | None = None
) -> tuple[dict[str, Any], dict[str, int]]:
    """Versión oficial + informe nuevo: lo nuevo se suma y, ante diferencias, manda lo ya oficial.

    Las diferencias que fueron conflictos se resuelven con ``patches`` (la decisión tomada).
    """
    data = copy.deepcopy(base.data)
    provenance = dict(base.provenance)
    for section, value in (report.data or {}).items():
        if section in SKIPPED_SECTIONS or value in (None, "", [], {}):
            continue
        if section not in data or data[section] in (None, "", [], {}):
            data[section] = copy.deepcopy(value)
            provenance[f"section::{section}"] = report.id
            for item in _items(data, section):
                if identity_of(item):
                    provenance.setdefault(f"{section}::{identity_of(item)}", report.id)
            continue
        if isinstance(value, list):
            data[section], provenance = _merge_list(
                section, data[section], value, provenance, report.id
            )
        elif isinstance(value, dict) and isinstance(data[section], dict):
            data[section] = _fill_missing(data[section], value)
    return apply_patches(data, patches or []), provenance


def apply_patches(data: dict[str, Any], patches: list[Patch]) -> dict[str, Any]:
    """Aplica las decisiones de una reconciliación sobre los datos consolidados."""
    result = copy.deepcopy(data)
    for patch in patches:
        items = result.get(patch["section"])
        if not isinstance(items, list):
            continue
        if patch["op"] == "set":
            for item in items:
                if isinstance(item, dict) and identity_of(item) == patch["identity"]:
                    item.update(patch["fields"])
        elif patch["op"] == "remove_item":
            result[patch["section"]] = [
                item
                for item in items
                if not (isinstance(item, dict) and identity_of(item) == patch["identity"])
            ]
    return result


def identity_of(item: Any) -> str:
    """Clave normalizada que identifica a un elemento de una lista (fármaco, dispositivo…)."""
    if not isinstance(item, dict):
        return ""
    for key in IDENTITY_KEYS:
        value = item.get(key)
        if isinstance(value, str) and value.strip():
            return normalize(value)
    return ""


def section_title(section: str) -> str:
    return section.replace("_", " ").capitalize()


def _set(report: Report, status: str) -> None:
    report.consolidation = status
    report.save(update_fields=["consolidation", "updated_at"])


def _items(data: dict[str, Any], section: str) -> list[dict[str, Any]]:
    value = data.get(section)
    return [i for i in value if isinstance(i, dict)] if isinstance(value, list) else []


def _differs(old: Any, new: Any) -> bool:
    if old in (None, "") or new in (None, ""):
        return False
    if isinstance(old, int | float) and isinstance(new, int | float):
        return abs(old - new) > max(1e-9, RELATIVE_TOLERANCE * max(abs(old), abs(new)))
    return normalize(str(old)) != normalize(str(new))


def _display(item: dict[str, Any], field: str) -> str:
    value = item.get(field)
    unit = item.get("unidad") if field == "dosis" else None
    return f"{value} {unit}".strip() if unit else str(value)


def _side(report: Report | None, value: str, evidence: str, patch: list[Patch]) -> dict[str, Any]:
    return {
        "reportId": report.id if report else None,
        "authorId": report.author_id if report else None,
        "authorName": (report.author.name or report.author.email) if report else "",
        "profession": report.profession if report else "",
        "value": value,
        "evidence": evidence,
        "patch": patch,
    }


def _value_conflict(
    section: str,
    id_key: str,
    identity: str,
    field: str,
    old: dict[str, Any],
    new: dict[str, Any],
    old_report: Report | None,
    new_report: Report,
) -> dict[str, Any]:
    def patch(item: dict[str, Any]) -> list[Patch]:
        fields = {field: item[field]}
        if field == "dosis" and item.get("unidad"):
            fields["unidad"] = item["unidad"]
        return [{"op": "set", "section": section, "identity": identity, "fields": fields}]

    name = new.get(id_key) or old.get(id_key)
    return {
        "key": f"{section}:{identity}:{field}",
        "kind": "value",
        "section": section,
        "label": f"{section_title(section)} · {name} · {FIELD_LABELS.get(field, field)}",
        "side_a": _side(
            old_report, _display(old, field), str(old.get("evidencia") or ""), patch(old)
        ),
        "side_b": _side(
            new_report, _display(new, field), str(new.get("evidencia") or ""), patch(new)
        ),
    }


def _allergy_conflicts(
    base: ConsolidatedVersion, sources: dict[int, Report], report: Report
) -> list[dict[str, Any]]:
    """Alergia en un informe e indicación de un fármaco de ese grupo en el otro."""
    new_data = report.data or {}
    pairs = [
        (base.data, base.provenance, new_data, None),  # alergia oficial vs fármaco nuevo
        (new_data, None, base.data, base.provenance),  # alergia nueva vs fármaco oficial
    ]
    found: list[dict[str, Any]] = []
    for allergy_data, allergy_prov, drug_data, drug_prov in pairs:
        for allergy in _items(allergy_data, "alergias"):
            group = _allergen_group(allergy.get("agente"))
            if not group:
                continue
            for section, id_key in DRUG_SECTIONS:
                for drug in _items(drug_data, section):
                    if not _in_group(drug, id_key, group):
                        continue
                    allergy_report = _owner(allergy_prov, "alergias", allergy, sources, report)
                    drug_report = _owner(drug_prov, section, drug, sources, report)
                    if allergy_report is drug_report:
                        continue
                    found.append(
                        _allergy_conflict(allergy, allergy_report, section, drug, drug_report)
                    )
    return found


def _allergy_conflict(
    allergy: dict[str, Any],
    allergy_report: Report | None,
    section: str,
    drug: dict[str, Any],
    drug_report: Report | None,
) -> dict[str, Any]:
    drug_name = drug.get("nombre") or drug.get("farmaco")
    return {
        "key": f"alergia:{identity_of(allergy)}:{section}:{identity_of(drug)}",
        "kind": "allergy",
        "section": section,
        "label": f"Alergia a {allergy.get('agente')} · indicación de {drug_name}",
        "side_a": _side(
            allergy_report,
            f"Alergia a {allergy.get('agente')}"
            + (f" ({allergy['reaccion']})" if allergy.get("reaccion") else ""),
            str(allergy.get("evidencia") or ""),
            # La alergia prevalece: se retira la indicación del fármaco.
            [{"op": "remove_item", "section": section, "identity": identity_of(drug)}],
        ),
        "side_b": _side(
            drug_report,
            f"Indicación de {drug_name}",
            str(drug.get("evidencia") or ""),
            # La indicación prevalece: se descarta la alergia registrada.
            [{"op": "remove_item", "section": "alergias", "identity": identity_of(allergy)}],
        ),
    }


def _owner(
    provenance: dict[str, int] | None,
    section: str,
    item: dict[str, Any],
    sources: dict[int, Report],
    new_report: Report,
) -> Report | None:
    if provenance is None:
        return new_report
    return sources.get(provenance.get(f"{section}::{identity_of(item)}"))


def _allergen_group(agent: Any) -> str:
    plain = normalize(str(agent or ""))
    return next((group for group in ALLERGEN_GROUPS if group in plain), "")


def _in_group(drug: dict[str, Any], id_key: str, group: str) -> bool:
    names = [normalize(str(drug.get(key) or "")) for key in (id_key, "principio_activo")]
    return any(term in name for name in names for term in ALLERGEN_GROUPS[group])


def _source_reports(base: ConsolidatedVersion) -> dict[int, Report]:
    ids = {int(report_id) for report_id in base.provenance.values() if report_id}
    reports = Report.objects.filter(id__in=ids).select_related("author")
    return {report.id: report for report in reports}


def _provenance_of(data: dict[str, Any], source: Report | None) -> dict[str, int]:
    """Procedencia de una versión nueva: todo lo que contiene viene de ``source``."""
    if source is None:
        return {}
    provenance: dict[str, int] = {}
    for section, value in data.items():
        if section in SKIPPED_SECTIONS or value in (None, "", [], {}):
            continue
        provenance[f"section::{section}"] = source.id
        for item in _items(data, section):
            if identity_of(item):
                provenance[f"{section}::{identity_of(item)}"] = source.id
    return provenance


def _merge_list(
    section: str,
    base_items: list[Any],
    new_items: list[Any],
    provenance: dict[str, int],
    report_id: int,
) -> tuple[list[Any], dict[str, int]]:
    merged = list(base_items)
    index = {identity_of(i): n for n, i in enumerate(merged) if identity_of(i)}
    for item in new_items:
        identity = identity_of(item)
        if identity and identity in index:
            merged[index[identity]] = _fill_missing(merged[index[identity]], item)
        elif not any(_same(item, existing) for existing in merged):
            merged.append(copy.deepcopy(item))
            if identity:
                provenance.setdefault(f"{section}::{identity}", report_id)
    return merged, provenance


def _fill_missing(base: Any, new: Any) -> Any:
    """``base`` con los huecos (vacíos) completados desde ``new``; lo ya informado se respeta."""
    if isinstance(base, dict) and isinstance(new, dict):
        return {key: _fill_missing(base.get(key), new.get(key)) for key in {**new, **base}}
    return new if base in (None, "", [], {}) else base


def _same(a: Any, b: Any) -> bool:
    return json.dumps(a, sort_keys=True, ensure_ascii=False) == json.dumps(
        b, sort_keys=True, ensure_ascii=False
    )


def now():
    return timezone.now()
