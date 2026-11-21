"""Registro clínico y traspasos con datos reales: pacientes asignados, informes guardados."""

from __future__ import annotations

import copy
from datetime import UTC, datetime, timedelta

import pytest
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client
from django.utils import timezone

from apps.clinical_templates import services as template_services
from apps.recordings.models import Patient, Recording
from apps.transcription import episode_services as episodes
from apps.transcription import extraction_services as extraction
from apps.transcription import reconciliation_services as rec
from apps.transcription import report_services
from apps.transcription.models import Conflict, ExtractedRecord, Report, Transcription
from apps.users import shifts

API = f"/{settings.URL_PREFIX}/api/episodes"
User = get_user_model()


@pytest.fixture(autouse=True)
def templates(db, monkeypatch):
    template_services.sync_templates_from_files()
    monkeypatch.setattr(
        extraction,
        "complete_json",
        lambda messages: (_ for _ in ()).throw(ValueError("sin modelo")),
    )


@pytest.fixture()
def doctor(db):
    user = User.objects.create_user(
        email="medico@x.cl", password="pw", name="Dr. Rojas", profession="medico"
    )
    shifts.start_shift(user)
    return user


@pytest.fixture()
def nurse(db):
    user = User.objects.create_user(
        email="enf@x.cl", password="pw", name="EU Soto", profession="enfermeria"
    )
    shifts.start_shift(user)
    return user


@pytest.fixture()
def patient(doctor, nurse):
    patient = Patient.objects.create(name="Juan Pérez", identifier="1-9", bed="Box 7")
    patient.assigned_to.add(doctor, nurse)
    return patient


def _report(author, patient, profession, data, hours_ago=1.0) -> Report:
    recording = Recording.objects.create(
        professional=author,
        patient=patient,
        audio=SimpleUploadedFile("a.wav", b"x", "audio/wav"),
        mime_type="audio/wav",
        size_bytes=1,
        source=Recording.Source.UPLOAD,
        recorded_at=timezone.now() - timedelta(hours=hours_ago),
        profession=profession,
    )
    transcription = Transcription.objects.create(
        recording=recording, status="done", text="x", language="es", model_id="w"
    )
    record = ExtractedRecord.objects.create(
        transcription=transcription,
        template=template_services.get_active_template_for_profession(profession),
        status="done",
        data=copy.deepcopy(data),
    )
    report = report_services.generate_report(record)
    report.validated_sections = [t.id for t in report_services.topics_of(report)]
    report.save()
    return report_services.validate_report(report)


DOCTOR_DATA = {
    "metadatos": {"cama": "Box 7"},
    "resumen_24h": "Shock séptico en resolución.",
    "diagnosticos": [{"descripcion": "Shock séptico", "estado": "confirmado"}],
    "control_hemodinamico": [{"pam": 68, "frecuencia_cardiaca": 94}],
    "control_respiratorio": [{"soporte": "VMI", "saturacion_o2": 96}],
    "drogas_infusion": [{"farmaco": "norepinefrina", "dosis": 0.15, "unidad": "mcg/kg/min"}],
    "medicamentos": [{"nombre": "meropenem", "dosis": 1, "unidad": "g"}],
    "alertas": [{"descripcion": "Hipoxemia", "severidad": "alta"}],
    "pendientes": [
        {"descripcion": "Control de lactato", "plazo": "en 2 h"},
        {"descripcion": "Evaluar prono", "plazo": "sin plazo claro"},
    ],
    "indicaciones": [{"descripcion": "Mantener PAM >= 65"}],
    "metas_del_dia": [{"parametro": "Saturación", "objetivo": ">= 92 %"}],
}


def test_records_are_the_patients_assigned_to_the_active_user(doctor, nurse, patient):
    other = Patient.objects.create(name="Ajeno", identifier="2-7", bed="Box 1")
    other.assigned_to.add(nurse)
    _report(doctor, patient, "medico", DOCTOR_DATA)

    records = episodes.episode_records(doctor)

    assert [r["episode"]["label"] for r in records] == ["Juan Pérez (1-9) · Box 7"]
    assert next(iter(episodes.episode_records(nurse)))["episode"]["label"].startswith("Ajeno")
    assert "isFictional" not in records[0]["episode"]


def test_a_saved_report_becomes_an_encounter_with_entries_measurements_and_plan(doctor, patient):
    report = _report(doctor, patient, "medico", DOCTOR_DATA)

    record = episodes.episode_records(doctor)[0]
    [encounter] = record["encounters"]
    kinds = [entry["kind"] for entry in encounter["entries"]]
    texts = " ".join(entry["text"] for entry in encounter["entries"])

    assert encounter["id"] == f"enc-{report.id}"
    assert encounter["authorId"] == str(doctor.id)
    assert {"assessment", "vitals", "intervention", "plan"} <= set(kinds)
    assert "Shock séptico en resolución." in texts
    assert "Noradrenalina 0.15 mcg/kg/min" in texts  # homologado
    assert "Mantener PAM >= 65" in texts and "Saturación de oxígeno >= 92 %" in texts
    vitals = next(e for e in encounter["entries"] if e["kind"] == "vitals")
    assert {m["code"]: m["value"] for m in vitals["measurements"]} == {
        "pam": "68",
        "hr": "94",
        "spo2": "96",
    }
    assert all(e["status"] == "validated" for e in encounter["entries"])
    assert record["professionals"][0]["role"] == "Médico UCI"
    assert record["professionals"][0]["discipline"] == "medicine"
    assert record["shifts"][0]["id"] == encounter["shiftId"]


def test_drafts_never_enter_the_clinical_record(doctor, patient):
    _report(doctor, patient, "medico", DOCTOR_DATA)
    recording = Recording.objects.create(
        professional=doctor,
        patient=patient,
        audio=SimpleUploadedFile("b.wav", b"x", "audio/wav"),
        mime_type="audio/wav",
        size_bytes=1,
        source="upload",
        recorded_at=timezone.now() - timedelta(minutes=5),
        profession="medico",
    )
    transcription = Transcription.objects.create(
        recording=recording, status="done", text="x", language="es", model_id="w"
    )
    draft = ExtractedRecord.objects.create(
        transcription=transcription,
        template=template_services.get_active_template_for_profession("medico"),
        status="done",
        data=DOCTOR_DATA,
    )
    report_services.generate_report(draft)  # queda por validar

    assert len(episodes.episode_records(doctor)[0]["encounters"]) == 1


def test_pending_tasks_come_from_the_reports_with_parsed_deadlines(doctor, patient):
    _report(doctor, patient, "medico", DOCTOR_DATA, hours_ago=1)

    pendings = episodes.episode_records(doctor)[0]["pendings"]

    assert [p["title"] for p in pendings] == ["Control de lactato", "Evaluar prono"]
    assert pendings[0]["dueAt"] is not None and pendings[1]["dueAt"] is None
    assert all(p["status"] == "open" and p["ownerId"] == str(doctor.id) for p in pendings)
    assert pendings[0]["sourceEncounterId"].startswith("enc-")


def test_closing_a_pending_is_saved_and_only_for_assigned_patients(doctor, nurse, patient):
    _report(doctor, patient, "medico", DOCTOR_DATA)
    stranger = User.objects.create_user(email="z@x.cl", password="pw")
    pending_id = episodes.episode_records(doctor)[0]["pendings"][0]["id"]
    client = Client()
    client.force_login(nurse)
    outsider = Client()
    outsider.force_login(stranger)
    url = f"{API}/{patient.id}/pendings/{pending_id}/close"

    assert outsider.post(url).status_code == 409
    closed = client.post(url)
    assert closed.status_code == 200 and closed.json()["status"] == "done"
    assert closed.json()["closedById"] == str(nurse.id)
    assert client.post(url).status_code == 409  # ya cerrado
    record = episodes.episode_records(doctor)[0]
    assert next(p for p in record["pendings"] if p["id"] == pending_id)["status"] == "done"


def test_open_conflicts_show_up_in_the_patients_record(doctor, nurse, patient):
    _report(doctor, patient, "medico", {**DOCTOR_DATA, "pendientes": []})
    _report(
        nurse,
        patient,
        "enfermeria",
        {
            "metadatos": {"cama": "Box 7"},
            "drogas_infusion": [{"farmaco": "noradrenalina", "dosis": 0.3, "unidad": "mcg/kg/min"}],
        },
    )

    record = episodes.episode_records(doctor)[0]

    [conflict] = record["openConflicts"]
    assert "0.15" in conflict["description"] and "0.3" in conflict["description"]
    encounter_ids = {e["id"] for e in record["encounters"]}
    assert (
        set(conflict["sourceEncounterIds"]) <= encounter_ids
        and len(conflict["sourceEncounterIds"]) == 2
    )
    rec.accept_other(Conflict.objects.get(), doctor)  # resuelto: deja de ser un conflicto abierto
    assert episodes.episode_records(doctor)[0]["openConflicts"] == []


def test_team_lists_everyone_for_names_and_real_colleagues_as_recipients(doctor, nurse):
    stranger = User.objects.create_user(email="sinprof@x.cl", password="pw", name="Sin Profesión")

    team = episodes.team(doctor)

    assert team["meId"] == str(doctor.id)
    assert {p["name"] for p in team["professionals"]} == {"Dr. Rojas", "EU Soto", "Sin Profesión"}
    assert team["recipientIds"] == [str(nurse.id)]  # ni tú ni cuentas sin profesión
    assert str(stranger.id) not in team["recipientIds"]


def test_a_handoff_is_saved_for_both_sides_and_shares_the_patients(doctor, nurse, patient):
    _report(doctor, patient, "medico", DOCTOR_DATA)
    third = User.objects.create_user(
        email="kine@x.cl", password="pw", name="Klgo", profession="kinesiologia"
    )
    client = Client()
    client.force_login(doctor)
    snapshot = {"episodeId": str(patient.id), "episodeLabel": patient.reference, "pendings": []}

    sent = client.post(
        f"{API}/handoffs",
        {"to_id": third.id, "note": " Vigilar PAM ", "snapshots": [snapshot]},
        content_type="application/json",
    )

    assert sent.status_code == 201, sent.content
    body = sent.json()
    assert (body["fromId"], body["toId"], body["note"]) == (
        str(doctor.id),
        str(third.id),
        "Vigilar PAM",
    )
    assert third in patient.assigned_to.all()  # quien recibe pasa a ver al paciente
    for user, direction in ((doctor, "fromId"), (third, "toId")):
        c = Client()
        c.force_login(user)
        assert [h[direction] for h in c.get(f"{API}/handoffs").json()] == [str(user.id)]
    nobody = Client()
    nobody.force_login(nurse)
    assert nobody.get(f"{API}/handoffs").json() == []


def test_a_handoff_rejects_foreign_patients_missing_recipients_and_yourself(doctor, nurse, patient):
    foreign = Patient.objects.create(name="Ajeno", identifier="3-3", bed="Box 3")
    client = Client()
    client.force_login(doctor)

    def post(to_id, snapshots):
        return client.post(
            f"{API}/handoffs",
            {"to_id": to_id, "snapshots": snapshots},
            content_type="application/json",
        ).status_code

    mine = {"episodeId": str(patient.id)}
    assert post(nurse.id, [{"episodeId": str(foreign.id)}]) == 409  # paciente que no es tuyo
    assert post(doctor.id, [mine]) == 409  # a ti mismo
    assert post(nurse.id, []) == 409  # sin pacientes
    assert post(99999, [mine]) == 409  # destinatario inexistente


def test_shifts_are_clinical_day_and_night_in_chile_time():
    day = episodes._shift(datetime(2026, 11, 20, 15, 0, tzinfo=UTC))  # 12:00 en Chile
    night = episodes._shift(datetime(2026, 11, 21, 2, 0, tzinfo=UTC))  # 23:00 del 20
    early = episodes._shift(datetime(2026, 11, 21, 8, 0, tzinfo=UTC))  # 05:00 del 21: noche del 20

    assert day["label"] == "Día 20/11"
    assert night["label"] == early["label"] == "Noche 20/11"
    assert night["id"] == early["id"] == "shift-night-2026-11-20"


def test_patients_can_be_split_between_different_recipients(doctor, nurse, patient):
    second = Patient.objects.create(name="María Díaz", identifier="4-4", bed="Box 2")
    second.assigned_to.add(doctor)
    kine = User.objects.create_user(
        email="kine@x.cl", password="pw", name="Klgo", profession="kinesiologia"
    )
    client = Client()
    client.force_login(doctor)

    def send(to, patient_obj):
        snapshot = {"episodeId": str(patient_obj.id), "episodeLabel": patient_obj.reference}
        return client.post(
            f"{API}/handoffs",
            {"to_id": to.id, "snapshots": [snapshot]},
            content_type="application/json",
        )

    assert send(nurse, patient).status_code == 201
    assert send(kine, second).status_code == 201

    # Cada persona recibió solo los pacientes que se le entregaron.
    assert kine in second.assigned_to.all() and kine not in patient.assigned_to.all()
    assert nurse in patient.assigned_to.all() and nurse not in second.assigned_to.all()
    sent = client.get(f"{API}/handoffs").json()
    assert {(h["toId"], tuple(s["episodeId"] for s in h["snapshots"])) for h in sent} == {
        (str(nurse.id), (str(patient.id),)),
        (str(kine.id), (str(second.id),)),
    }
