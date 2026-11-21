"""Resumen global y síntesis por áreas de un paciente."""

from __future__ import annotations

import pytest
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client
from django.utils import timezone

from apps.clinical_templates import services as template_services
from apps.recordings.models import Patient, Recording
from apps.transcription import extraction_services, summary_services
from apps.transcription.models import (
    ConsolidatedVersion,
    ExtractedRecord,
    Report,
    Transcription,
)
from apps.transcription.tasks import generate_patient_synthesis

API_URL = f"/{settings.URL_PREFIX}/api/patients"
User = get_user_model()

DATA = {
    "metadatos": {"cama": "Box 4", "dia_estada_uci": 3},
    "resumen_24h": "Paciente estable, sin novedades.",
    "diagnosticos": [{"descripcion": "Sepsis abdominal", "estado": "activo"}],
    "alertas": [],
    "control_respiratorio": [{"soporte": "VMI", "fio2": 40, "saturacion_o2": 95}],
    "drogas_infusion": [
        {"farmaco": "Noradrenalina", "dosis": 0.1, "unidad": "mcg/kg/min", "tendencia": "estable"}
    ],
    "pendientes": [{"descripcion": "Control de lactato", "plazo": "6 h"}],
    "dato_inesperado": {"valor": "x"},
}
MODEL_REPLY = {
    "resumen_global": "Varón en UCI por sepsis abdominal, estable.",
    "areas": {
        "Diagnósticos y alertas": "Sepsis abdominal activa.",
        "Respiratorio": "Ventilación mecánica con FiO2 40 %.",
        "Hemodinamia": "Noradrenalina 0,1 mcg/kg/min estable.",
        "Nutrición": "Esta área no venía en los datos y debe ignorarse.",
    },
}


@pytest.fixture(autouse=True)
def isolated_cache(monkeypatch, tmp_path):
    monkeypatch.setenv("PIPELINE_CACHE_DIR", str(tmp_path))


@pytest.fixture()
def doctor(db):
    return User.objects.create_user(email="medico@example.com", password="pw", name="Dr. Rojas")


@pytest.fixture()
def patient(doctor):
    created = Patient.objects.create(name="Marta Silva", identifier="21.001.001-1", bed="Box 4")
    created.assigned_to.add(doctor)
    return created


@pytest.fixture()
def version(patient):
    return ConsolidatedVersion.objects.create(
        patient=patient, version=1, data=DATA, reason=ConsolidatedVersion.Reason.OFFICIAL
    )


def _model(monkeypatch, reply=None, error=None) -> list[int]:
    calls: list[int] = []

    def complete_json(messages):
        calls.append(1)
        if error:
            raise error
        return reply

    monkeypatch.setattr(extraction_services, "complete_json", complete_json)
    return calls


def _by_area(overview) -> dict:
    return {area.area: area for area in overview.areas}


def test_overview_without_a_version_is_empty(doctor, patient):
    overview = summary_services.patient_overview(doctor, patient)

    assert overview.version == 0
    assert overview.globalSummary == ""
    assert overview.areas == []


def test_model_writes_the_global_summary_and_each_area(
    monkeypatch, doctor, patient, version, synthesis_jobs
):
    _model(monkeypatch, MODEL_REPLY)

    summary_services.patient_overview(doctor, patient)
    generate_patient_synthesis.run(*synthesis_jobs.pop())
    overview = summary_services.patient_overview(doctor, patient)
    areas = _by_area(overview)

    assert overview.version == 1
    assert overview.globalSummary == MODEL_REPLY["resumen_global"]
    assert areas["Respiratorio"].summary == "Ventilación mecánica con FiO2 40 %."
    assert "Noradrenalina" in areas["Hemodinamia"].summary
    assert areas["Respiratorio"].informed is True
    assert areas["Nutrición"].summary == ""
    assert areas["Nutrición"].informed is False


def test_sections_that_fit_no_area_go_to_others(monkeypatch, doctor, patient, version):
    _model(monkeypatch, MODEL_REPLY)

    areas = _by_area(summary_services.patient_overview(doctor, patient))

    assert areas["Otros"].informed is True
    assert areas["Otros"].sections == ["dato_inesperado"]
    assert "control_respiratorio" in areas["Respiratorio"].sections


def test_others_is_left_out_when_nothing_is_unplaced(monkeypatch, doctor, patient, version):
    version.data = {key: value for key, value in DATA.items() if key != "dato_inesperado"}
    version.save()
    _model(monkeypatch, MODEL_REPLY)

    assert "Otros" not in _by_area(summary_services.patient_overview(doctor, patient))


def test_overview_returns_available_data_before_running_one_job(
    monkeypatch, doctor, patient, version, synthesis_jobs
):
    calls = _model(monkeypatch, MODEL_REPLY)

    first = summary_services.patient_overview(doctor, patient)
    second = summary_services.patient_overview(doctor, patient)

    assert first == second
    assert first.synthesisPending is True
    assert first.globalSummary == DATA["resumen_24h"]
    assert "VMI" in _by_area(first)["Respiratorio"].summary
    assert calls == []
    assert len(synthesis_jobs) == 1

    generate_patient_synthesis.run(*synthesis_jobs.pop())
    third = summary_services.patient_overview(doctor, patient)

    assert third.synthesisPending is False
    assert third.globalSummary == MODEL_REPLY["resumen_global"]
    assert synthesis_jobs == []
    assert len(calls) == 1


def test_without_a_model_the_areas_are_written_by_hand(
    monkeypatch, doctor, patient, version, synthesis_jobs
):
    _model(monkeypatch, error=ValueError("sin modelo"))

    summary_services.patient_overview(doctor, patient)
    generate_patient_synthesis.run(*synthesis_jobs.pop())
    overview = summary_services.patient_overview(doctor, patient)
    areas = _by_area(overview)

    assert overview.globalSummary == "Paciente estable, sin novedades."
    assert overview.synthesisPending is False
    assert "Noradrenalina" in areas["Hemodinamia"].summary
    assert "VMI" in areas["Respiratorio"].summary
    assert "Control de lactato" in areas["Plan y pendientes"].summary


def test_overview_stops_polling_when_the_worker_does_not_run(
    monkeypatch, doctor, patient, version, synthesis_jobs
):
    monkeypatch.setattr(summary_services, "time", lambda: 100)
    assert summary_services.patient_overview(doctor, patient).synthesisPending is True

    expires_at = 100 + summary_services.SYNTHESIS_PENDING_TTL
    monkeypatch.setattr(summary_services, "time", lambda: expires_at)
    overview = summary_services.patient_overview(doctor, patient)

    assert overview.synthesisPending is False
    assert overview.globalSummary == DATA["resumen_24h"]
    assert len(synthesis_jobs) == 1


def test_endpoint_returns_the_overview_of_an_assigned_patient(
    monkeypatch, doctor, patient, version
):
    _model(monkeypatch, MODEL_REPLY)
    client = Client()
    client.force_login(doctor)

    response = client.get(f"{API_URL}/{patient.id}/overview")

    assert response.status_code == 200, response.content
    body = response.json()
    assert body["globalSummary"] == DATA["resumen_24h"]
    assert {area["area"] for area in body["areas"]} >= {"Hemodinamia", "Respiratorio"}


def test_endpoint_hides_patients_assigned_to_someone_else(monkeypatch, doctor, patient, version):
    _model(monkeypatch, MODEL_REPLY)
    stranger = User.objects.create_user(email="otra@example.com", password="pw")
    client = Client()
    client.force_login(stranger)

    assert client.get(f"{API_URL}/{patient.id}/overview").status_code == 404


def _report(author, patient, profession, consolidation) -> Report:
    """Un informe guardado con la cadena mínima de dictado, transcripción y registro."""
    template_services.sync_templates_from_files()
    recording = Recording.objects.create(
        professional=author,
        audio=SimpleUploadedFile("a.wav", b"x", "audio/wav"),
        mime_type="audio/wav",
        size_bytes=1,
        source=Recording.Source.UPLOAD,
        recorded_at=timezone.now(),
        patient=patient,
    )
    transcription = Transcription.objects.create(
        recording=recording,
        status=Transcription.Status.DONE,
        text="x",
        language="spanish",
        model_id="m",
    )
    record = ExtractedRecord.objects.create(
        transcription=transcription,
        template=template_services.get_active_template_for_profession(profession),
        status=ExtractedRecord.Status.DONE,
        data={},
    )
    return Report.objects.create(
        extracted_record=record,
        author=author,
        profession=profession,
        patient=patient,
        status=Report.Status.DONE,
        data={},
        consolidation=consolidation,
    )


def test_contributors_are_professions_not_people(monkeypatch, doctor, patient, version):
    nurse = User.objects.create_user(email="enfermera@example.com", password="pw", name="EU Soto")
    kine = User.objects.create_user(email="kine@example.com", password="pw", name="Klgo. Muñoz")
    official = _report(doctor, patient, "medico", Report.Consolidation.OFFICIAL)
    clash = _report(nurse, patient, "enfermeria", Report.Consolidation.RECONCILING)
    merged = _report(kine, patient, "kinesiologia", Report.Consolidation.MERGED)
    version.provenance = {
        "section::control_respiratorio": merged.id,
        "drogas_infusion::noradrenalina": official.id,
        "section::pendientes": official.id,
        "section::diagnosticos": official.id,
    }
    version.save()
    _model(monkeypatch, MODEL_REPLY)

    overview = summary_services.patient_overview(doctor, patient)
    areas = _by_area(overview)

    assert [(c.profession, c.reportCount, c.inConflict) for c in overview.contributors] == [
        ("medico", 1, False),
        ("enfermeria", 1, True),
        ("kinesiologia", 1, False),
    ]
    assert clash.consolidation == Report.Consolidation.RECONCILING
    assert areas["Respiratorio"].contributors == ["kinesiologia"]
    assert areas["Hemodinamia"].contributors == ["medico"]
    assert areas["Plan y pendientes"].contributors == ["medico"]
    assert areas["Nutrición"].contributors == []
    dumped = overview.model_dump_json()
    assert "EU Soto" not in dumped and "Klgo" not in dumped and "Dr. Rojas" not in dumped


def test_the_model_never_receives_professional_names(
    monkeypatch, doctor, patient, version, synthesis_jobs
):
    version.data = {**DATA, "metadatos": {**DATA["metadatos"], "nombre_profesional": "Dr. Rojas"}}
    version.save()
    seen: list[str] = []

    def complete_json(messages):
        seen.extend(message.content for message in messages)
        return MODEL_REPLY

    monkeypatch.setattr(extraction_services, "complete_json", complete_json)

    summary_services.patient_overview(doctor, patient)
    generate_patient_synthesis.run(*synthesis_jobs.pop())

    sent = "\n".join(seen)
    assert "Dr. Rojas" not in sent and "nombre_profesional" not in sent
    assert "No menciones nombres" in sent
