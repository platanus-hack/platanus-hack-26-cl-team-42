"""Consolidación (versión oficial) y reconciliación de conflictos entre informes."""

from __future__ import annotations

import copy
import json
from datetime import UTC, datetime
from io import StringIO

import pytest
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client

from apps.clinical_templates import services as template_services
from apps.recordings.models import Patient, Recording
from apps.transcription import extraction_services as extraction
from apps.transcription import reconciliation_services as rec
from apps.transcription import report_services
from apps.transcription.models import (
    ConsolidatedVersion,
    ExternalConsult,
    ExtractedRecord,
    Report,
    Transcription,
)
from apps.users import shifts

API_URL = f"/{settings.URL_PREFIX}/api/transcription"
User = get_user_model()


class FakeModel:
    name = "fake"

    def __init__(self, replies):
        self.replies = list(replies)

    def complete(self, messages):
        return self.replies.pop(0)


@pytest.fixture(autouse=True)
def templates(db):
    template_services.sync_templates_from_files()


@pytest.fixture(autouse=True)
def offline_model(monkeypatch):
    # Sin modelo: homologación y sugerencias usan sus reglas.
    monkeypatch.setattr(extraction, "_extraction_model", lambda: FakeModel([]))


@pytest.fixture()
def doctor(db):
    return User.objects.create_user(
        email="medico@example.com", password="pw", name="Dr. Rojas", profession="medico"
    )


@pytest.fixture()
def nurse(db):
    return User.objects.create_user(
        email="enfermera@example.com", password="pw", name="EU Soto", profession="enfermeria"
    )


@pytest.fixture()
def specialist(db):
    return User.objects.create_user(
        email="infecto@example.com", password="pw", name="Dra. Fuentes", profession="especialista"
    )


@pytest.fixture(autouse=True)
def on_duty(doctor, nurse, specialist):
    """La app conoce los turnos: por defecto los tres profesionales están de turno."""
    for professional in (doctor, nurse, specialist):
        shifts.start_shift(professional)


@pytest.fixture()
def patient(doctor, nurse):
    patient = Patient.objects.create(name="Juan Pérez Soto", identifier="11.111.111-1", bed="Box 7")
    patient.assigned_to.add(doctor, nurse)
    return patient


def _base_data() -> dict:
    """Lo que dicta el médico: noradrenalina 0,15, CVC yugular y piperacilina/tazobactam."""
    return {
        "metadatos": {"tipo_profesional": "medico", "cama": "Box 7", "dia_estada_uci": 3},
        "drogas_infusion": [
            {
                "farmaco": "norepinefrina",
                "categoria": "vasoactivo",
                "dosis": 0.15,
                "unidad": "mcg/kg/min",
                "evidencia": "norepinefrina a 0,15",
            }
        ],
        "medicamentos": [
            {
                "nombre": "pip/tazo",
                "dosis": 4.5,
                "unidad": "g",
                "via": "EV",
                "evidencia": "pip tazo",
            }
        ],
        "dispositivos_invasivos": [
            {"tipo": "CVC", "ubicacion": "yugular derecha", "evidencia": "CVC yugular derecha"}
        ],
        "alergias": [],
        "pendientes": [{"descripcion": "Control de lactato", "plazo": "14:00"}],
    }


def _nurse_data() -> dict:
    """Lo que dicta enfermería: tres choques con lo del médico, más datos nuevos."""
    return {
        "metadatos": {"tipo_profesional": "enfermeria", "cama": "Box 7"},
        "drogas_infusion": [
            {
                "farmaco": "noradrenalina",
                "categoria": "vasoactivo",
                "dosis": 0.3,
                "unidad": "mcg/kg/min",
                "evidencia": "noradrenalina a 0,3",
            }
        ],
        "dispositivos_invasivos": [
            {"tipo": "vía central", "ubicacion": "subclavia derecha", "evidencia": "subclavia"}
        ],
        "alergias": [
            {
                "agente": "penicilina",
                "reaccion": "rash cutáneo",
                "evidencia": "alergia a penicilina",
            }
        ],
        "balance_hidrico": {"balance_ml": 450, "diuresis_ml": 1200},
    }


def _save_report(author, patient, profession, data) -> Report:
    """Un informe que su autor validó y guardó (sin pasar por el modelo)."""
    recording = Recording.objects.create(
        professional=author,
        audio=SimpleUploadedFile("a.wav", b"x", "audio/wav"),
        mime_type="audio/wav",
        size_bytes=1,
        source=Recording.Source.UPLOAD,
        recorded_at="2026-11-19T10:00:00Z",
        patient=patient,
        patient_reference=patient.reference,
        profession=profession,
    )
    transcription = Transcription.objects.create(
        recording=recording, status=Transcription.Status.DONE, text="x", language="es", model_id="w"
    )
    record = ExtractedRecord.objects.create(
        transcription=transcription,
        template=template_services.get_active_template_for_profession(profession),
        status=ExtractedRecord.Status.DONE,
        data=copy.deepcopy(data),
    )
    report = report_services.generate_report(record)
    for point in report_services.pending_review_items(report):
        report_services.review_item(report, point.id)
    return report_services.validate_report(report)


def _conflicts(report: Report):
    return {c.kind + ":" + c.section: c for c in report.reconciliations.get().conflicts.all()}


def test_first_saved_report_becomes_the_official_version(doctor, patient):
    report = _save_report(doctor, patient, "medico", _base_data())

    version = ConsolidatedVersion.objects.get(patient=patient)
    assert (version.version, version.is_current, version.reason) == (1, True, "official")
    assert report.consolidation == Report.Consolidation.OFFICIAL
    assert version.data["drogas_infusion"][0]["farmaco"] == "Noradrenalina"  # homologado


def test_a_consistent_report_is_merged_into_a_new_version(doctor, nurse, patient):
    _save_report(doctor, patient, "medico", _base_data())
    consistent = {
        "metadatos": {"tipo_profesional": "enfermeria"},
        "drogas_infusion": [{"farmaco": "norepinefrina", "dosis": 0.15, "unidad": "mcg/kg/min"}],
        "balance_hidrico": {"balance_ml": 450},
    }

    report = _save_report(nurse, patient, "enfermeria", consistent)

    versions = list(ConsolidatedVersion.objects.filter(patient=patient).order_by("version"))
    assert [v.version for v in versions] == [1, 2]
    assert [v.is_current for v in versions] == [False, True]
    assert report.consolidation == Report.Consolidation.MERGED
    assert versions[1].data["balance_hidrico"] == {"balance_ml": 450}
    assert "balance_hidrico" not in versions[0].data  # la anterior se conserva intacta


def test_conflicting_report_opens_a_reconciliation_and_keeps_the_official_version(
    doctor, nurse, patient
):
    _save_report(doctor, patient, "medico", _base_data())

    report = _save_report(nurse, patient, "enfermeria", _nurse_data())

    assert report.consolidation == Report.Consolidation.RECONCILING
    assert ConsolidatedVersion.objects.filter(patient=patient).count() == 1
    conflicts = _conflicts(report)
    assert set(conflicts) == {
        "value:drogas_infusion",
        "value:dispositivos_invasivos",
        "allergy:medicamentos",
    }
    dose = conflicts["value:drogas_infusion"]
    assert (dose.side_a["value"], dose.side_b["value"]) == ("0.15 mcg/kg/min", "0.3 mcg/kg/min")
    assert dose.side_a["authorId"] == doctor.id and dose.side_b["authorId"] == nurse.id
    assert "Dr. Rojas" in dose.explanation and "EU Soto" in dose.explanation
    allergy = conflicts["allergy:medicamentos"]
    assert "riesgo de seguridad" in allergy.explanation


def test_resolving_every_conflict_creates_the_current_version_and_keeps_history(
    doctor, nurse, patient
):
    _save_report(doctor, patient, "medico", _base_data())
    report = _save_report(nurse, patient, "enfermeria", _nurse_data())
    conflicts = _conflicts(report)

    # El médico acepta el valor de enfermería para la dosis; enfermería, el del médico para el CVC.
    rec.accept_other(conflicts["value:drogas_infusion"], doctor)
    assert report.reconciliations.get().status == "open"
    rec.accept_other(conflicts["value:dispositivos_invasivos"], nurse)
    assert ConsolidatedVersion.objects.filter(patient=patient).count() == 1
    # Alergia vs indicación: el médico acepta la alergia (se retira la indicación).
    rec.accept_other(conflicts["allergy:medicamentos"], doctor)

    reconciliation = report.reconciliations.get()
    report.refresh_from_db()
    current = ConsolidatedVersion.objects.get(patient=patient, is_current=True)
    assert (reconciliation.status, report.consolidation) == ("resolved", "consolidated")
    assert (current.version, current.reason) == (2, "reconciliation")
    assert current.data["drogas_infusion"][0]["dosis"] == 0.3
    assert current.data["dispositivos_invasivos"][0]["ubicacion"] == "yugular derecha"
    assert current.data["alergias"][0]["agente"] == "penicilina"
    assert current.data["medicamentos"] == []  # la indicación contraindicada se retiró
    assert current.data["balance_hidrico"] == {"balance_ml": 450, "diuresis_ml": 1200}
    old = ConsolidatedVersion.objects.get(patient=patient, version=1)
    assert old.data["drogas_infusion"][0]["dosis"] == 0.15 and not old.is_current


def test_a_proposal_needs_the_other_side_to_agree(doctor, nurse, patient):
    _save_report(doctor, patient, "medico", _base_data())
    conflict = _conflicts(_save_report(nurse, patient, "enfermeria", _nurse_data()))[
        "value:drogas_infusion"
    ]

    rec.propose(conflict, doctor, side=None, value="0,2 mcg/kg/min")
    conflict.refresh_from_db()
    with pytest.raises(rec.ReconciliationError):
        rec.agree(conflict, doctor)  # no puede aceptar su propia propuesta
    rec.agree(conflict, nurse)

    conflict.refresh_from_db()
    assert conflict.status == "resolved"
    assert conflict.resolution["mode"] == "consensus"
    current = ConsolidatedVersion.objects.get(patient=patient, is_current=True)
    assert current.version == 1  # quedan otros choques abiertos


def test_deciding_alone_requires_the_other_to_be_off_shift(doctor, nurse, patient):
    _save_report(doctor, patient, "medico", _base_data())
    conflict = _conflicts(_save_report(nurse, patient, "enfermeria", _nurse_data()))[
        "value:dispositivos_invasivos"
    ]

    # Con la contraparte de turno hay que llegar a consenso.
    with pytest.raises(rec.ReconciliationError):
        rec.decide(conflict, doctor, side="a", value=None)
    assert rec.to_conflict_out(conflict, doctor).canDecide is False

    shifts.end_shift(nurse)  # termina el turno de enfermería: la app lo sabe sola
    assert rec.to_conflict_out(conflict, doctor).canDecide is True
    rec.decide(conflict, doctor, side="a", value=None)

    conflict.refresh_from_db()
    assert conflict.resolution["mode"] == "off_shift"
    assert conflict.resolution["side"] == "a"


def test_a_participant_who_is_off_shift_cannot_act(doctor, nurse, patient):
    _save_report(doctor, patient, "medico", _base_data())
    conflict = _conflicts(_save_report(nurse, patient, "enfermeria", _nurse_data()))[
        "value:drogas_infusion"
    ]
    shifts.end_shift(nurse)

    for action in (
        lambda: rec.accept_other(conflict, nurse),
        lambda: rec.propose(conflict, nurse, "a", None),
        lambda: rec.add_note(conflict, nurse, "Sigo aquí"),
    ):
        with pytest.raises(rec.ReconciliationError, match="fuera de turno"):
            action()
    view = rec.to_conflict_out(conflict, nurse)
    assert (view.iAmOnShift, view.canAccept) == (False, False)
    assert {p.name: p.onShift for p in view.participantsShift} == {
        "Dr. Rojas": True,
        "EU Soto": False,
    }


def test_only_participants_write_notes_and_the_record_is_kept(doctor, nurse, specialist, patient):
    _save_report(doctor, patient, "medico", _base_data())
    conflict = _conflicts(_save_report(nurse, patient, "enfermeria", _nurse_data()))[
        "value:drogas_infusion"
    ]

    rec.add_note(conflict, doctor, "La bomba marcaba 0,15 a las 08:00.")
    rec.add_note(conflict, nurse, "A las 11:00 subió a 0,3 por hipotensión.")
    with pytest.raises(rec.ReconciliationError):
        rec.add_note(conflict, specialist, "Me meto yo")

    kinds = [(n.kind, n.author.name if n.author else None) for n in conflict.notes.all()]
    assert ("note", "Dr. Rojas") in kinds and ("note", "EU Soto") in kinds
    assert kinds[0][0] == "system"  # el agente dejó el aviso inicial


def test_external_opinion_goes_to_the_on_shift_professional_the_system_picks(
    doctor, nurse, specialist, patient
):
    _save_report(doctor, patient, "medico", _base_data())
    conflict = _conflicts(_save_report(nurse, patient, "enfermeria", _nurse_data()))[
        "allergy:medicamentos"
    ]
    rec.add_note(
        conflict, doctor, "Juan Pérez tolera bien la piperacilina en Box 7, según Dr. Rojas."
    )

    consult = rec.request_external(conflict, doctor)  # sin elegir a nadie: lo decide el sistema

    assert consult.consultant == specialist
    for secret in ("Juan", "Pérez", "Soto", "11.111.111-1", "Box 7", "Dr. Rojas", "EU Soto"):
        assert secret not in consult.brief
    assert "Consulta clínica anonimizada" in consult.brief
    assert "penicilina" in consult.brief.lower()
    with pytest.raises(rec.ReconciliationError):
        rec.request_external(conflict, nurse)  # ya se pidió a ese profesional

    rec.reply_external(consult, specialist, "Evitaría el betalactámico hasta aclarar la alergia.")
    consult.refresh_from_db()
    assert consult.status == "answered"
    assert conflict.notes.filter(kind="external", author=specialist).exists()
    # El externo puede aportar notas, pero no ve ni decide el conflicto.
    assert rec.get_conflict(specialist, conflict.id) is None


def test_no_external_opinion_when_nobody_suitable_is_on_shift(doctor, nurse, specialist, patient):
    _save_report(doctor, patient, "medico", _base_data())
    conflict = _conflicts(_save_report(nurse, patient, "enfermeria", _nurse_data()))[
        "allergy:medicamentos"
    ]
    shifts.end_shift(specialist)

    assert rec.to_conflict_out(conflict, doctor).guidance.externalCandidate is None
    with pytest.raises(rec.ReconciliationError, match="de turno"):
        rec.request_external(conflict, doctor)


def test_the_agent_guides_each_conflict_automatically(doctor, nurse, specialist, patient):
    _save_report(doctor, patient, "medico", _base_data())
    conflicts = _conflicts(_save_report(nurse, patient, "enfermeria", _nurse_data()))

    allergy = rec.to_conflict_out(conflicts["allergy:medicamentos"], doctor).guidance
    device = rec.to_conflict_out(conflicts["value:dispositivos_invasivos"], nurse).guidance

    # La orientación ya está ahí desde que se abrió el conflicto: nadie la pide.
    assert allergy.recommendedSide == "a" and "alergia debería prevalecer" in allergy.suggestion
    assert allergy.externalProfession == "especialista"
    assert allergy.externalCandidate.name == "Dra. Fuentes"
    # Un dato con dos valores se resuelve entre quienes lo reportaron: sin opinión externa.
    assert device.externalRecommended is False and device.externalCandidate is None


def test_the_model_refines_the_guidance_in_the_background_and_it_is_cached(
    monkeypatch, doctor, nurse, patient
):
    _save_report(doctor, patient, "medico", _base_data())
    conflict = _conflicts(_save_report(nurse, patient, "enfermeria", _nurse_data()))[
        "value:drogas_infusion"
    ]
    reply = {
        "sugerencia": "La bomba es la fuente más confiable: verifiquen su registro.",
        "postura": "b",
        "profesion_adicional": "kinesiologia",
        "motivo": "Puede confirmar la tolerancia hemodinámica.",
    }
    model = FakeModel([json.dumps(reply)])
    monkeypatch.setattr(extraction, "_extraction_model", lambda: model)

    rec.refine_guidance(conflict.id)
    rec.refine_guidance(conflict.id)  # la segunda sale de la caché: sin más respuestas del modelo

    conflict.refresh_from_db()
    assert conflict.guidance["suggestion"].startswith("La bomba es la fuente")
    assert conflict.guidance["recommended_side"] == "b"
    # Aunque el modelo sugiera consultar a alguien, un valor distinto no se deriva a un externo.
    assert conflict.guidance["external_profession"] is None
    assert conflict.guidance["external_recommended"] is False


def test_api_lists_the_reconciliation_for_both_professionals(doctor, nurse, specialist, patient):
    _save_report(doctor, patient, "medico", _base_data())
    report = _save_report(nurse, patient, "enfermeria", _nurse_data())
    as_doctor, as_nurse, as_stranger = Client(), Client(), Client()
    as_doctor.force_login(doctor)
    as_nurse.force_login(nurse)
    as_stranger.force_login(specialist)

    for client in (as_doctor, as_nurse):
        listed = client.get(f"{API_URL}/reconciliations").json()
        assert len(listed) == 1 and len(listed[0]["conflicts"]) == 3
    assert as_stranger.get(f"{API_URL}/reconciliations").json() == []
    assert set(listed[0]["participants"]) == {"Dr. Rojas", "EU Soto"}

    conflict = as_doctor.get(f"{API_URL}/reconciliations").json()[0]["conflicts"][0]
    assert conflict["myRole"] in ("a", "b") and conflict["canAccept"] is True
    assert conflict["iAmOnShift"] is True and conflict["guidance"]["suggestion"]
    assert {p["name"]: p["onShift"] for p in conflict["participantsShift"]} == {
        "Dr. Rojas": True,
        "EU Soto": True,
    }
    base = f"{API_URL}/conflicts/{conflict['id']}"
    note = as_doctor.post(
        f"{base}/notes", {"body": "Reviso la bomba."}, content_type="application/json"
    )
    assert note.status_code == 200 and note.json()["notes"][-1]["body"] == "Reviso la bomba."
    assert as_stranger.post(f"{base}/accept").status_code == 404
    assert as_stranger.post(f"{base}/external").status_code == 404
    accepted = as_nurse.post(f"{base}/accept")
    assert accepted.status_code == 200 and accepted.json()["status"] == "resolved"
    assert as_nurse.post(f"{base}/accept").status_code == 409  # ya resuelto
    assert Report.objects.get(pk=report.pk).reconciliations.get().conflicts.filter(status="open")


def test_reports_list_only_shows_saved_reports(doctor, nurse, patient):
    saved = _save_report(doctor, patient, "medico", _base_data())
    draft = _draft(nurse, patient)
    as_doctor, as_nurse = Client(), Client()
    as_doctor.force_login(doctor)
    as_nurse.force_login(nurse)

    ids = [r["id"] for r in as_nurse.get(f"{API_URL}/reports").json()]

    assert ids == [str(saved.id)]  # el borrador de enfermería no aparece, ni para su autora
    assert as_nurse.get(f"{API_URL}/reports/{draft.id}").status_code == 200  # pero puede abrirlo
    assert as_doctor.get(f"{API_URL}/reports/{draft.id}").status_code == 404


def _draft(author, patient) -> Report:
    recording = Recording.objects.create(
        professional=author,
        audio=SimpleUploadedFile("b.wav", b"x", "audio/wav"),
        mime_type="audio/wav",
        size_bytes=1,
        source=Recording.Source.UPLOAD,
        recorded_at="2026-11-19T12:00:00Z",
        patient=patient,
        profession="enfermeria",
    )
    transcription = Transcription.objects.create(
        recording=recording, status="done", text="x", language="es", model_id="w"
    )
    record = ExtractedRecord.objects.create(
        transcription=transcription,
        template=template_services.get_active_template_for_profession("enfermeria"),
        status="done",
        data=_nurse_data(),
    )
    return report_services.generate_report(record)


def test_patient_summary_comes_from_the_current_official_version(doctor, nurse, patient):
    _save_report(doctor, patient, "medico", _base_data())
    report = _save_report(nurse, patient, "enfermeria", _nurse_data())
    client = Client()
    client.force_login(doctor)
    summary_url = f"/{settings.URL_PREFIX}/api/patients/{patient.id}"

    before = client.get(f"{summary_url}/summary").json()
    for conflict in report.reconciliations.get().conflicts.all():
        # Quien reportó primero (el médico) cede: acepta el valor del otro profesional.
        rec.accept_other(conflict, doctor)
    after = client.get(f"{summary_url}/summary").json()
    versions = client.get(f"{summary_url}/versions").json()

    assert before["version"] == 1
    assert after["version"] == 2 and after["versionReason"] == "reconciliation"
    assert [v["version"] for v in versions] == [2, 1]
    assert versions[0]["isCurrent"] is True
    old = client.get(f"{summary_url}/versions/1").json()
    assert old["data"]["drogas_infusion"][0]["dosis"] == 0.15


# --- Escenario de demo: los audios de sample_audios/conflictos, de punta a punta, sin modelo ---

DEMO_DIR = __import__("pathlib").Path(__file__).parents[2] / "sample_audios" / "conflictos"


def _run_demo_audio(author, patient, name: str) -> Report:
    """Sube un audio de demo y lo lleva (con las cachés) hasta su informe guardado."""
    from apps.recordings.services import create_recording
    from apps.transcription import services as transcription_services

    recording = create_recording(
        professional=author,
        audio=SimpleUploadedFile(
            f"{name}.wav", (DEMO_DIR / f"{name}.wav").read_bytes(), "audio/wav"
        ),
        source=Recording.Source.UPLOAD,
        recorded_at=datetime(2026, 11, 19, 10, 0, tzinfo=UTC),
        patient=patient,
    )
    transcription = Transcription.objects.create(
        recording=recording, language="spanish", model_id="cache"
    )
    transcription_services.run_transcription(transcription.id)
    record = ExtractedRecord.objects.get(transcription=transcription)
    extraction.run_extraction(record.id)
    report = Report.objects.get(extracted_record=record)
    assert report.status == Report.Status.REVIEW, report.error
    for point in report_services.pending_review_items(report):
        report_services.review_item(report, point.id)
    return report_services.validate_report(report)


def test_demo_audios_tell_the_conflict_story_offline(monkeypatch, doctor, nurse, patient):
    from apps.transcription import pipeline_cache

    monkeypatch.setenv("PIPELINE_CACHE_DIR", str(pipeline_cache.DEFAULT_CACHE_DIR))
    monkeypatch.setattr(extraction, "_enqueue", lambda record_id: None)

    official = _run_demo_audio(doctor, patient, "Dr. Rojas - Médico UCI - 19-11-2026 08-00")
    clash = _run_demo_audio(nurse, patient, "EU Soto - Enfermería - 19-11-2026 11-00")
    clean = _run_demo_audio(doctor, patient, "Klgo. Muñoz - Kinesiología - 19-11-2026 14-00")

    assert official.consolidation == Report.Consolidation.OFFICIAL
    assert official.profession == "medico" and clash.profession == "enfermeria"
    # Homologación: «norepinefrina» y «noradrenalina» son el mismo fármaco, así que el choque
    # es de dosis y no de nombre.
    assert set(_conflicts(clash)) == {
        "value:drogas_infusion",
        "value:dispositivos_invasivos",
        "allergy:medicamentos",
    }
    assert clash.consolidation == Report.Consolidation.RECONCILING
    # El informe de kinesiología es coherente con la versión oficial: se incorpora sin choques.
    assert clean.consolidation == Report.Consolidation.MERGED


@pytest.mark.parametrize("is_admin", [False, True])
def test_the_patient_team_sees_the_reconciliation_read_only(doctor, nurse, patient, is_admin):
    bystander = User.objects.create_user(
        email="otro@localhost", password="pw", is_staff=is_admin, is_superuser=is_admin
    )
    patient.assigned_to.add(bystander)
    shifts.start_shift(bystander)
    _save_report(doctor, patient, "medico", _base_data())
    _save_report(nurse, patient, "enfermeria", _nurse_data())
    client = Client()
    client.force_login(bystander)

    listed = client.get(f"{API_URL}/reconciliations").json()
    conflict = listed[0]["conflicts"][0]

    assert len(listed[0]["conflicts"]) == 3
    assert conflict["myRole"] is None and conflict["canAccept"] is False
    # Puede mirar, pero no actuar: solo resuelven quienes reportaron.
    assert client.post(f"{API_URL}/conflicts/{conflict['id']}/accept").status_code == 404
    assert (
        client.post(
            f"{API_URL}/conflicts/{conflict['id']}/notes",
            {"body": "hola"},
            content_type="application/json",
        ).status_code
        == 404
    )


def test_external_opinion_is_only_for_conceptual_discrepancies(doctor, nurse, specialist, patient):
    _save_report(doctor, patient, "medico", _base_data())
    conflicts = _conflicts(_save_report(nurse, patient, "enfermeria", _nurse_data()))
    value = conflicts["value:drogas_infusion"]

    assert rec.to_conflict_out(value, doctor).guidance.externalRecommended is False
    with pytest.raises(rec.ReconciliationError, match="conceptuales"):
        rec.request_external(value, doctor)


def test_the_external_brief_carries_the_clinical_context(doctor, nurse, specialist, patient):
    _save_report(doctor, patient, "medico", _base_data())
    conflict = _conflicts(_save_report(nurse, patient, "enfermeria", _nurse_data()))[
        "allergy:medicamentos"
    ]

    brief = rec.request_external(conflict, doctor).brief

    assert "Contexto clínico del paciente" in brief
    assert "Día 3 de estadía en UCI" in brief
    assert "Soporte respiratorio" not in brief or "VMI" in brief or "ventilación" in brief.lower()
    assert "Noradrenalina" in brief and "Piperacilina/tazobactam" in brief
    assert "alergia a penicilina" in brief.lower()  # lo que dijo quien reportó la alergia
    for secret in ("Juan", "Pérez", "11.111.111-1", "Box 7", "Dr. Rojas", "EU Soto"):
        assert secret not in brief


def test_the_remaining_professional_decides_knowing_what_the_other_reported(doctor, nurse, patient):
    _save_report(doctor, patient, "medico", _base_data())
    conflict = _conflicts(_save_report(nurse, patient, "enfermeria", _nurse_data()))[
        "value:drogas_infusion"
    ]
    shifts.end_shift(nurse)

    rec.decide(conflict, doctor, side="a", value=None)

    conflict.refresh_from_db()
    decision = conflict.notes.filter(kind="system").last().body
    assert "con conocimiento de la discrepancia" in decision
    assert "EU Soto (que había registrado «0.3 mcg/kg/min»)" in decision


def test_demo_external_consultant_has_no_patients_assigned():
    from django.core.management import call_command

    from apps.recordings.services import patients_of

    User.objects.create_user(email="demo@example.com", password="pw")
    consultant = User.objects.create_user(
        email="especialista@localhost", password="pw", profession="especialista"
    )
    call_command("load_demo_patients", "demo@example.com", stdout=StringIO())

    assert patients_of(consultant).count() == 0


def test_drafts_are_listed_only_when_asked_and_only_to_their_author(doctor, nurse, patient):
    _save_report(doctor, patient, "medico", _base_data())
    draft = _draft(nurse, patient)
    as_doctor, as_nurse = Client(), Client()
    as_doctor.force_login(doctor)
    as_nurse.force_login(nurse)
    url = f"{API_URL}/reports?patient_id={patient.id}"

    assert [r["status"] for r in as_nurse.get(url).json()] == ["done"]
    mine = as_nurse.get(f"{url}&include_drafts=true").json()
    assert {r["status"] for r in mine} == {"done", "review"}
    assert str(draft.id) in {r["id"] for r in mine}
    # El borrador de enfermería nunca llega a los demás, ni pidiéndolo.
    assert [r["status"] for r in as_doctor.get(f"{url}&include_drafts=true").json()] == ["done"]


def test_stale_or_unjustified_consults_are_not_shown_to_the_consultant(
    doctor, nurse, specialist, patient
):
    _save_report(doctor, patient, "medico", _base_data())
    conflicts = _conflicts(_save_report(nurse, patient, "enfermeria", _nurse_data()))
    allergy = conflicts["allergy:medicamentos"]
    value = conflicts["value:dispositivos_invasivos"]
    # Una consulta antigua sobre un dato con dos valores (hoy ya no se puede crear).
    ExternalConsult.objects.create(
        conflict=value, requested_by=doctor, consultant=specialist, brief="vieja"
    )
    valid = rec.request_external(allergy, doctor)

    assert [c.id for c in rec.list_external_consults(specialist)] == [str(valid.id)]

    rec.accept_other(allergy, doctor)  # la alergia se resuelve: la consulta pendiente ya no importa
    assert rec.list_external_consults(specialist) == []
    assert rec.get_external_consult(specialist, valid.id) is None


# --- Triage de la bandeja: criticidad, prioridad de visita y tareas pendientes ---------------


def test_inbox_triage_ranks_by_criticality_and_time_since_the_last_visit(doctor, nurse, patient):
    from datetime import timedelta

    from django.utils import timezone

    from apps.transcription.triage_services import triage_for

    quiet = Patient.objects.create(name="Paciente Sin Informe", identifier="9-9", bed="Box 1")
    _save_report(doctor, patient, "medico", _base_data())  # noradrenalina (vasoactivo): alto
    now = timezone.now()

    triage = triage_for(
        [patient.id, quiet.id], {patient.id: now - timedelta(hours=5), quiet.id: None}, now
    )

    sick, unknown = triage[patient.id], triage[quiet.id]
    assert sick.criticality == "high" and sick.criticality_label == "Alto"
    # Un paciente de criticidad alta se visita cada ~4 h: a las 5 h ya toca.
    assert (sick.visit_priority, sick.priority_score) == ("now", 1.25)
    assert sick.pending_tasks == 1  # «Control de lactato»
    assert unknown.criticality == "unknown" and unknown.visit_priority == "unknown"

    def at(hours: float):
        return triage_for([patient.id], {patient.id: now - timedelta(hours=hours)}, now)[patient.id]

    assert (at(0.5).visit_priority, at(0.5).priority_score) == ("ok", 0.12)
    assert at(3).visit_priority == "soon"  # 3 de 4 h
    never = triage_for([patient.id], {patient.id: None}, now)[patient.id]
    assert never.visit_priority == "now"  # sin ninguna visita registrada


def test_patient_list_exposes_the_triage(doctor, nurse, patient):
    _save_report(doctor, patient, "medico", _base_data())
    client = Client()
    client.force_login(doctor)

    listed = client.get(f"/{settings.URL_PREFIX}/api/patients").json()[0]

    assert listed["criticality"] == "high" and listed["criticalityLabel"] == "Alto"
    assert listed["pendingTasks"] == 1
    assert listed["visitPriority"] in ("now", "soon", "ok")
    assert isinstance(listed["priorityScore"], float)


# --- Visibilidad: solo quien tiene el paciente asignado; el resto, solo la versión anonimizada ---


def test_only_professionals_with_the_patient_assigned_see_the_conflicts(
    doctor, nurse, specialist, patient
):
    bystander = User.objects.create_user(email="otro@localhost", password="pw")
    _save_report(doctor, patient, "medico", _base_data())
    report = _save_report(nurse, patient, "enfermeria", _nurse_data())
    reconciliation = report.reconciliations.get()
    conflict = reconciliation.conflicts.first()

    assert len(rec.list_reconciliations(doctor)) == 1  # participante asignado
    assert rec.list_reconciliations(bystander) == []  # sin el paciente: nada
    assert rec.list_reconciliations(specialist) == []  # ni siquiera el externo
    assert rec.get_reconciliation(bystander, reconciliation.id) is None
    assert rec.get_conflict(bystander, conflict.id) is None

    # Si el paciente se traspasa, quien lo entregó deja de ver el conflicto y de poder actuar.
    patient.assigned_to.remove(nurse)
    assert rec.list_reconciliations(nurse) == []
    assert rec.get_conflict(nurse, conflict.id) is None
    with pytest.raises(rec.ReconciliationError, match="ya no está asignado"):
        rec.accept_other(conflict, nurse)


def test_an_off_shift_participant_triggers_the_anonymized_case_for_a_third_party(
    doctor, nurse, specialist, patient
):
    _save_report(doctor, patient, "medico", _base_data())
    report = _save_report(nurse, patient, "enfermeria", _nurse_data())
    conflicts = _conflicts(report)
    allergy, dose = conflicts["allergy:medicamentos"], conflicts["value:drogas_infusion"]
    assert not allergy.consults.exists()  # con los dos de turno no hay nada que enviar

    shifts.end_shift(nurse)
    rec.list_reconciliations(doctor)  # el agente lo detecta al revisar los conflictos
    rec.list_reconciliations(doctor)  # y no repite el envío

    consult = allergy.consults.get()
    assert consult.consultant == specialist
    for secret in ("Juan", "Pérez", "11.111.111-1", "Box 7", "Dr. Rojas", "EU Soto"):
        assert secret not in consult.brief
    assert "Contexto clínico del paciente" in consult.brief
    note = allergy.notes.filter(kind="system").last().body
    assert "EU Soto está fuera de turno" in note and "anonimizado" in note
    # El tercero recibe solo la versión anonimizada, no el conflicto.
    assert [c.id for c in rec.list_external_consults(specialist)] == [str(consult.id)]
    assert rec.list_reconciliations(specialist) == []
    # Un dato con dos valores no se deriva: lo decide quien sigue de turno.
    assert not dose.consults.exists()


def test_the_anonymized_case_goes_out_when_the_conflict_opens_if_someone_is_already_off_shift(
    doctor, nurse, specialist, patient
):
    _save_report(doctor, patient, "medico", _base_data())
    shifts.end_shift(nurse)

    report = _save_report(nurse, patient, "enfermeria", _nurse_data())

    allergy = _conflicts(report)["allergy:medicamentos"]
    assert allergy.consults.get().consultant == specialist


def test_no_anonymized_case_is_sent_when_nobody_is_available(doctor, nurse, specialist, patient):
    _save_report(doctor, patient, "medico", _base_data())
    report = _save_report(nurse, patient, "enfermeria", _nurse_data())
    shifts.end_shift(nurse)
    shifts.end_shift(specialist)

    rec.list_reconciliations(doctor)

    assert not _conflicts(report)["allergy:medicamentos"].consults.exists()


def test_patient_list_flags_patients_with_open_conflicts(doctor, nurse, patient):
    quiet = Patient.objects.create(name="Sin Conflictos", identifier="7-7", bed="Box 2")
    quiet.assigned_to.add(doctor)
    bystander = User.objects.create_user(email="otro@localhost", password="pw")
    patient.assigned_to.add(bystander)
    _save_report(doctor, patient, "medico", _base_data())
    report = _save_report(nurse, patient, "enfermeria", _nurse_data())

    def counts(user):
        client = Client()
        client.force_login(user)
        listed = client.get(f"/{settings.URL_PREFIX}/api/patients").json()
        return {p["name"]: (p["openConflicts"], p["myOpenConflicts"]) for p in listed}

    # Los dos implicados tienen los 3 conflictos como suyos; un tercero del equipo, ninguno.
    assert counts(doctor) == {"Juan Pérez Soto": (3, 3), "Sin Conflictos": (0, 0)}
    assert counts(nurse) == {"Juan Pérez Soto": (3, 3)}
    assert counts(bystander) == {"Juan Pérez Soto": (3, 0)}

    for conflict in report.reconciliations.get().conflicts.all():
        rec.accept_other(conflict, doctor)
    assert counts(doctor)["Juan Pérez Soto"] == (0, 0)  # resueltos: ya no se marcan
