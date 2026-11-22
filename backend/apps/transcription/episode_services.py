"""Registro clínico y traspasos, armados con los datos reales de la app.

Cada paciente asignado al profesional es un «episodio». Sus informes guardados son las
atenciones (una por informe, con la hora del dictado) y de sus secciones salen las entradas
clínicas, los datos al corte, el plan y los pendientes. Los conflictos abiertos entre informes
aparecen como conflictos por revisar. Nada de esto está escrito a mano: sale de lo que
dictaron los profesionales.

Un traspaso guarda una copia fija de lo comunicado y deja al paciente también a cargo de quien
lo recibe, para que pueda verlo y cerrar sus pendientes.
"""

import re
from datetime import datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils import timezone

from apps.recordings.models import Patient
from apps.recordings.services import patients_of

from .models import Conflict, Handoff, PendingClosure, Report

CLINICAL_TZ = ZoneInfo("America/Santiago")
DAY_SHIFT_START = 8
NIGHT_SHIFT_START = 20
SHIFT_HOURS = 12
UNIT = "UCI"

PROFESSION_ROLE = {
    "medico": "Médico UCI",
    "especialista": "Especialista",
    "enfermeria": "Enfermería",
    "tens": "TENS",
    "kinesiologia": "Kinesiología",
    "nutricionista": "Nutrición",
}
DISCIPLINE = {
    "medico": "medicine",
    "especialista": "medicine",
    "enfermeria": "nursing",
    "tens": "nursing",
    "kinesiologia": "kinesiology",
    "nutricionista": "nutrition",
}
DEFAULT_DISCIPLINE = "medicine"


class EpisodeError(ValueError):
    """La acción no se puede hacer (paciente ajeno, pendiente inexistente o ya cerrado…)."""


# --------------------------------------------------------------------------------------
# Registros
# --------------------------------------------------------------------------------------


def episode_records(user, now: datetime | None = None) -> list[dict[str, Any]]:
    """Un registro por cada paciente asignado al profesional (ordenados por nombre)."""
    now = now or timezone.now()
    return [_record(user, patient, now) for patient in patients_of(user).order_by("name")]


def _record(user, patient: Patient, now: datetime) -> dict[str, Any]:
    reports = list(
        Report.objects.filter(patient=patient, status=Report.Status.DONE)
        .select_related("author", "extracted_record__transcription__recording")
        .order_by("extracted_record__transcription__recording__recorded_at", "id")
    )
    closures = {
        closure.pending_id: closure
        for closure in PendingClosure.objects.filter(patient=patient).select_related("closed_by")
    }
    encounters = [_encounter(patient, report) for report in reports]
    shifts = {}
    for encounter in encounters:
        shifts.setdefault(encounter["shiftId"], _shift(_occurred(encounter)))
    return {
        "episode": {
            "id": str(patient.id),
            "label": patient.reference,
            # Los datos por separado, para mostrarlos en columnas (nombre, RUT y box).
            "patient": {
                "name": patient.name,
                "identifier": patient.identifier,
                "bed": patient.bed,
            },
            "unit": UNIT,
            "admittedAt": patient.created_at.isoformat(),
            "cutoffAt": now.isoformat(),
        },
        "professionals": _authors(user, reports),
        "shifts": sorted(shifts.values(), key=lambda shift: shift["startsAt"]),
        "encounters": encounters,
        "pendings": [p for report in reports for p in _pendings(patient, report, closures)],
        "openConflicts": _open_conflicts(patient, {report.id for report in reports}),
    }


def _occurred(encounter: dict[str, Any]) -> datetime:
    return datetime.fromisoformat(encounter["occurredAt"])


def _encounter(patient: Patient, report: Report) -> dict[str, Any]:
    recording = report.extracted_record.transcription.recording
    author = report.author
    occurred = recording.recorded_at
    role = PROFESSION_ROLE.get(report.profession, report.profession)
    return {
        "id": _encounter_id(report.id),
        "episodeId": str(patient.id),
        "authorId": str(author.id),
        "shiftId": _shift(occurred)["id"],
        "occurredAt": occurred.isoformat(),
        "source": {
            "type": "audio_dictation",
            "label": f"Dictado de {_name(author)} · {role} (informe n.º {report.sequence})",
        },
        "entries": _entries(report),
        "chartedAt": report.charted_at.isoformat() if report.charted_at else None,
    }


def _encounter_id(report_id: int) -> str:
    return f"enc-{report_id}"


def _name(user) -> str:
    return user.name or user.email


def _authors(user, reports: list[Report]) -> list[dict[str, Any]]:
    """Los profesionales del registro: quienes dictaron algún informe del paciente, y tú."""
    professionals: dict[int, dict[str, Any]] = {}
    for report in reports:
        professionals[report.author_id] = _professional(report.author, report.profession)
    if user.id not in professionals:
        professionals[user.id] = _professional(user, user.profession)
    return list(professionals.values())


def _professional(user, profession: str) -> dict[str, Any]:
    profession = profession or user.profession
    return {
        "id": str(user.id),
        "name": _name(user),
        "role": PROFESSION_ROLE.get(profession, "Sin profesión definida"),
        "discipline": DISCIPLINE.get(profession, DEFAULT_DISCIPLINE),
    }


def _shift(moment: datetime) -> dict[str, Any]:
    """Turno clínico de un instante: «Día dd/mm» (8 a 20 h) o «Noche dd/mm», hora de Chile."""
    local = moment.astimezone(CLINICAL_TZ)
    if DAY_SHIFT_START <= local.hour < NIGHT_SHIFT_START:
        start, kind, label = (
            local.replace(hour=DAY_SHIFT_START, minute=0, second=0, microsecond=0),
            "day",
            "Día",
        )
    else:
        base = local if local.hour >= NIGHT_SHIFT_START else local - timedelta(days=1)
        start = base.replace(hour=NIGHT_SHIFT_START, minute=0, second=0, microsecond=0)
        kind, label = "night", "Noche"
    return {
        "id": f"shift-{kind}-{start:%Y-%m-%d}",
        "label": f"{label} {start:%d/%m}",
        "startsAt": start.isoformat(),
        "endsAt": (start + timedelta(hours=SHIFT_HOURS)).isoformat(),
    }


# --- entradas clínicas de un informe -------------------------------------------------------


def _entries(report: Report) -> list[dict[str, Any]]:
    data = report.data or {}
    found: list[tuple[str, str, list[dict[str, str]]]] = []

    summary = next(
        (
            data[k]
            for k in ("resumen_24h", "evaluacion", "motivo_interconsulta")
            if _text(data.get(k))
        ),
        None,
    )
    diagnoses = _join(
        f"{i['descripcion']}" + (f" ({i['estado']})" if i.get("estado") else "")
        for i in _items(data, "diagnosticos")
        if i.get("descripcion")
    )
    alerts = _join(
        f"{i['descripcion']}" + (f" ({i['severidad']})" if i.get("severidad") else "")
        for i in _items(data, "alertas")
        if i.get("descripcion")
    )
    if summary:
        found.append(("assessment", str(summary).strip(), []))
    if diagnoses:
        found.append(("assessment", f"Diagnósticos: {diagnoses}.", []))
    if alerts:
        found.append(("assessment", f"Alertas: {alerts}.", []))

    vitals_text, measurements = _vitals(data)
    if vitals_text:
        found.append(("vitals", vitals_text, measurements))

    infusions = _join(
        _drug(i, "farmaco") for i in _items(data, "drogas_infusion") if i.get("farmaco")
    )
    medicines = _join(_drug(i, "nombre") for i in _items(data, "medicamentos") if i.get("nombre"))
    if infusions:
        found.append(("intervention", f"Drogas en infusión: {infusions}.", []))
    if medicines:
        found.append(("intervention", f"Medicamentos: {medicines}.", []))
    techniques = _join(
        i["tecnica"] + (f" ({i['respuesta']})" if i.get("respuesta") else "")
        for i in _items(data, "intervenciones")
        if i.get("tecnica")
    )
    if techniques:
        found.append(("intervention", f"Intervenciones: {techniques}.", []))

    plan = _join(
        f"{label}: {_join(texts)}"
        for label, texts in (
            ("Indicaciones", _texts(data, "indicaciones", "descripcion")),
            (
                "Recomendaciones",
                _texts(data, "recomendaciones_al_tratante", "descripcion")
                + _texts(data, "recomendaciones_equipo", "descripcion"),
            ),
            (
                "Metas",
                _texts(data, "metas_del_dia", "objetivo", prefix="parametro")
                + _texts(data, "objetivos_terapeuticos", "objetivo"),
            ),
        )
        if texts
    )
    if plan:
        found.append(("plan", f"{plan}.", []))

    return [
        {
            "id": f"ent-{report.id}-{index}",
            "kind": kind,
            "text": text,
            "status": "validated",
            **({"measurements": measurements} if measurements else {}),
        }
        for index, (kind, text, measurements) in enumerate(found)
    ]


def _vitals(data: dict[str, Any]) -> tuple[str, list[dict[str, str]]]:
    hemodynamics = (_items(data, "control_hemodinamico") or [{}])[-1]
    respiratory = (_items(data, "control_respiratorio") or [{}])[-1]
    measured = [
        ("pam", "PAM", hemodynamics.get("pam"), "mmHg"),
        ("hr", "FC", hemodynamics.get("frecuencia_cardiaca"), "lpm"),
        ("rr", "FR", respiratory.get("frecuencia_respiratoria"), "rpm"),
        ("spo2", "SatO2", respiratory.get("saturacion_o2"), "%"),
    ]
    sis, dia = hemodynamics.get("presion_sistolica"), hemodynamics.get("presion_diastolica")
    if sis is not None and dia is not None:
        measured.append(("pa", "PA", f"{sis}/{dia}", "mmHg"))
    measurements = [
        {"code": code, "label": label, "value": str(value), "unit": unit}
        for code, label, value, unit in measured
        if value is not None
    ]
    support = respiratory.get("soporte")
    parts = [f"{m['label']} {m['value']} {m['unit']}" for m in measurements]
    if support:
        parts.append(f"soporte {support}")
    return (f"Controles: {', '.join(parts)}." if parts else ""), measurements


def _drug(item: dict[str, Any], name_key: str) -> str:
    dose = item.get("dosis")
    amount = f" {dose} {item.get('unidad') or ''}".rstrip() if dose is not None else ""
    return f"{item[name_key]}{amount}"


def _items(data: dict[str, Any], section: str) -> list[dict[str, Any]]:
    value = data.get(section)
    return [i for i in value if isinstance(i, dict)] if isinstance(value, list) else []


def _texts(data: dict[str, Any], section: str, key: str, prefix: str | None = None) -> list[str]:
    texts = []
    for item in _items(data, section):
        if item.get(key):
            lead = f"{item[prefix]} " if prefix and item.get(prefix) else ""
            texts.append(f"{lead}{item[key]}")
    return texts


def _text(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _join(parts) -> str:
    return "; ".join(part for part in parts if part)


# --- pendientes y conflictos -----------------------------------------------------------------


def _pendings(
    patient: Patient, report: Report, closures: dict[str, PendingClosure]
) -> list[dict[str, Any]]:
    recorded = report.extracted_record.transcription.recording.recorded_at
    pendings = []
    for index, item in enumerate(_items(report.data or {}, "pendientes")):
        if not item.get("descripcion"):
            continue
        pending_id = f"pend-{report.id}-{index}"
        closure = closures.get(pending_id)
        due = _due(item.get("plazo"), recorded)
        pendings.append(
            {
                "id": pending_id,
                "episodeId": str(patient.id),
                "title": item["descripcion"],
                "status": "done" if closure else "open",
                "ownerId": str(report.author_id),
                "dueAt": due.isoformat() if due else None,
                "sourceEncounterId": _encounter_id(report.id),
                **(
                    {
                        "closedAt": closure.closed_at.isoformat(),
                        "closedById": str(closure.closed_by_id),
                    }
                    if closure
                    else {}
                ),
            }
        )
    return pendings


def _due(deadline: Any, recorded: datetime) -> datetime | None:
    """Plazo escrito a mano («14:00», «en 2 h», «mañana 08:00») como instante, si se entiende."""
    if not isinstance(deadline, str):
        return None
    text = deadline.strip().lower()
    local = recorded.astimezone(CLINICAL_TZ)
    relative = re.fullmatch(r"(?:en\s+)?(\d+)\s*(?:h|hr|hrs|horas?)", text)
    if relative:
        return recorded + timedelta(hours=int(relative.group(1)))
    clock = re.fullmatch(r"(?:(mañana)\s+)?(\d{1,2}):(\d{2})", text)
    if clock:
        due = local.replace(
            hour=int(clock.group(2)), minute=int(clock.group(3)), second=0, microsecond=0
        )
        if clock.group(1):
            due += timedelta(days=1)
        elif due < local:
            due += timedelta(days=1)
        return due
    return None


def _open_conflicts(patient: Patient, saved_report_ids: set[int]) -> list[dict[str, Any]]:
    conflicts = Conflict.objects.filter(
        reconciliation__patient=patient, status=Conflict.Status.OPEN
    ).order_by("id")
    result = []
    for conflict in conflicts:
        a, b = conflict.side_a, conflict.side_b
        sources = list(
            dict.fromkeys(
                _encounter_id(side["reportId"])
                for side in (a, b)
                if side["reportId"] in saved_report_ids
            )
        )
        if not sources:
            continue
        result.append(
            {
                "id": str(conflict.id),
                "description": (
                    f"{conflict.label}: «{a['value']}» ({a['authorName']}) frente a "
                    f"«{b['value']}» ({b['authorName']})."
                ),
                "sourceEncounterIds": sources,
            }
        )
    return result


# --------------------------------------------------------------------------------------
# Equipo, pendientes y traspasos
# --------------------------------------------------------------------------------------


def team(user) -> dict[str, Any]:
    """Quién eres, los profesionales (para mostrar nombres) y a quiénes puedes traspasar."""
    members = list(get_user_model().objects.filter(is_active=True).order_by("name", "email"))
    return {
        "meId": str(user.id),
        "professionals": [_professional(m, m.profession) for m in members],
        # Se traspasa a otros profesionales, no a cuentas sin profesión definida.
        "recipientIds": [str(m.id) for m in members if m.profession and m.id != user.id],
    }


def close_pending(user, patient_id: int, pending_id: str) -> dict[str, Any]:
    """Da por cerrado un pendiente de uno de tus pacientes."""
    patient = patients_of(user).filter(pk=patient_id).first()
    if patient is None:
        raise EpisodeError("El paciente no está asignado a tu cuenta.")
    record = _record(user, patient, timezone.now())
    pending = next((p for p in record["pendings"] if p["id"] == pending_id), None)
    if pending is None:
        raise EpisodeError("No existe ese pendiente.")
    if pending["status"] == "done":
        raise EpisodeError("El pendiente ya está cerrado.")
    closure = PendingClosure.objects.create(patient=patient, pending_id=pending_id, closed_by=user)
    return {
        **pending,
        "status": "done",
        "closedAt": closure.closed_at.isoformat(),
        "closedById": str(user.id),
    }


# --- pasar a la ficha institucional ----------------------------------------------------------


def pending_chart_counts(user, patient_ids: list[int]) -> dict[int, int]:
    """Cuántos informes propios y guardados de cada paciente faltan por pasar a la ficha."""
    counts = dict.fromkeys(patient_ids, 0)
    for patient_id in _own_saved_reports(user).filter(
        patient_id__in=patient_ids, charted_at__isnull=True
    ).values_list("patient_id", flat=True):
        counts[patient_id] += 1
    return counts


@transaction.atomic
def mark_charted(user, patient_id: int, encounter_ids: list[str]) -> list[str]:
    """Da por pasadas a la ficha las atenciones indicadas (solo las propias y aún por pasar).

    Se marcan exactamente las que el profesional copió: un informe guardado después de copiar
    sigue por pasar.
    """
    reports = _chartable(user, patient_id, encounter_ids).filter(charted_at__isnull=True)
    marked = [_encounter_id(report_id) for report_id in reports.values_list("id", flat=True)]
    reports.update(charted_at=timezone.now())
    return marked


@transaction.atomic
def unmark_charted(user, patient_id: int, encounter_ids: list[str]) -> list[str]:
    """Deshace la marca: las atenciones vuelven a quedar por pasar a la ficha."""
    reports = _chartable(user, patient_id, encounter_ids).filter(charted_at__isnull=False)
    unmarked = [_encounter_id(report_id) for report_id in reports.values_list("id", flat=True)]
    reports.update(charted_at=None)
    return unmarked


def _own_saved_reports(user):
    return Report.objects.filter(author=user, status=Report.Status.DONE)


def _chartable(user, patient_id: int, encounter_ids: list[str]):
    if not patients_of(user).filter(pk=patient_id).exists():
        raise EpisodeError("El paciente no está asignado a tu cuenta.")
    report_ids = {_report_id(encounter_id) for encounter_id in encounter_ids}
    if not report_ids:
        raise EpisodeError("Indica qué atenciones pasaste a la ficha.")
    reports = _own_saved_reports(user).filter(patient_id=patient_id, id__in=report_ids)
    if reports.count() != len(report_ids):
        raise EpisodeError("Solo puedes marcar tus propias atenciones guardadas de este paciente.")
    return reports


def _report_id(encounter_id: str) -> int:
    match = re.fullmatch(r"enc-(\d+)", encounter_id)
    if match is None:
        raise EpisodeError(f"Atención desconocida: {encounter_id}.")
    return int(match.group(1))


def list_handoffs(user) -> list[dict[str, Any]]:
    handoffs = Handoff.objects.filter(from_user=user) | Handoff.objects.filter(to_user=user)
    return [_handoff_out(handoff) for handoff in handoffs.distinct().order_by("-sent_at")]


@transaction.atomic
def send_handoff(user, to_id: int, note: str, snapshots: list[dict[str, Any]]) -> dict[str, Any]:
    """Envía una entrega con los pacientes indicados; quien la recibe pasa a verlos."""
    recipient = get_user_model().objects.filter(pk=to_id, is_active=True).first()
    if recipient is None:
        raise EpisodeError("No existe el destinatario.")
    if recipient.pk == user.pk:
        raise EpisodeError("El destinatario debe ser otra persona.")
    if not snapshots:
        raise EpisodeError("Elige al menos un paciente para traspasar.")
    mine = {str(p.id): p for p in patients_of(user)}
    patients = []
    for snapshot in snapshots:
        patient = mine.get(str(snapshot.get("episodeId")))
        if patient is None:
            raise EpisodeError("Solo puedes traspasar pacientes asignados a tu cuenta.")
        patients.append(patient)
    handoff = Handoff.objects.create(
        from_user=user, to_user=recipient, note=note.strip()[:1000], snapshots=snapshots
    )
    for patient in patients:
        patient.assigned_to.add(recipient)
    return _handoff_out(handoff)


def _handoff_out(handoff: Handoff) -> dict[str, Any]:
    return {
        "id": str(handoff.id),
        "fromId": str(handoff.from_user_id),
        "toId": str(handoff.to_user_id),
        "note": handoff.note,
        "sentAt": handoff.sent_at.isoformat(),
        "snapshots": handoff.snapshots,
    }
