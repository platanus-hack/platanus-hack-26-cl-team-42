"""Demo desplegada: datos cargados y el audio de Cristóbal Tubino, de punta a punta sin modelo."""

from __future__ import annotations

import pytest
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.utils import timezone

from apps.clinical_templates import services as template_services
from apps.recordings import deploy_demo
from apps.recordings.models import Patient, Recording
from apps.recordings.services import create_recording
from apps.transcription import extraction_services as extraction
from apps.transcription import pipeline_cache, report_services
from apps.transcription import services as transcription_services
from apps.transcription.models import (
    ConsolidatedVersion,
    ExtractedRecord,
    Handoff,
    Report,
    Transcription,
)

User = get_user_model()


class NoModel:
    name = "none"

    def complete(self, messages):
        raise RuntimeError("sin modelo")


@pytest.fixture(autouse=True)
def offline(db, monkeypatch):
    template_services.sync_templates_from_files()
    monkeypatch.setattr(extraction, "_extraction_model", lambda: NoModel())
    monkeypatch.setattr(extraction, "_enqueue", lambda record_id: None)
    monkeypatch.setenv("PIPELINE_CACHE_DIR", str(pipeline_cache.DEFAULT_CACHE_DIR))


def _load():
    call_command("load_deploy_demo", "--password", "una-clave-de-prueba")


def test_loads_the_team_the_patients_and_the_handoff():
    _load()

    tomas = User.objects.get(email="tomas.werth@localhost")
    cristobal = User.objects.get(email="cristobal.tubino@localhost")
    nelson = User.objects.get(email="nelson.salazar@localhost")
    assert [tomas.profession, cristobal.profession, nelson.profession] == [
        "medico",
        "kinesiologia",
        "kinesiologia",
    ]
    assert tomas.check_password("una-clave-de-prueba")
    patients = Patient.objects.all()
    assert sorted(patients.values_list("name", flat=True)) == [
        "Agustin Reyman",
        "Clemente Vial",
        "María Jesús Navarrete",
    ]
    # Cada paciente tiene su informe de Tomás y fue traspasado a Cristóbal (no a Nelson).
    assert Report.objects.filter(author=tomas, status=Report.Status.DONE).count() == 3
    assert Handoff.objects.get(from_user=tomas, to_user=cristobal)
    assert set(cristobal.patients.all()) == set(patients)
    assert tomas.patients.count() == 0  # quien entrega deja de tener a los pacientes
    assert nelson.patients.count() == 0


def test_the_three_patients_have_three_different_visit_urgencies():
    from apps.transcription import inbox_services as inbox
    from apps.transcription.triage_services import triage_for

    _load()
    cristobal = User.objects.get(email="cristobal.tubino@localhost")
    patients = {p.name: p for p in cristobal.patients.all()}
    ids = [p.id for p in patients.values()]
    states = inbox.inbox_states(cristobal, ids)

    triage = triage_for(ids, {pid: states[pid].last_dictation_at for pid in ids})

    clemente, maria, agustin = (
        triage[patients[name].id]
        for name in ("Clemente Vial", "María Jesús Navarrete", "Agustin Reyman")
    )
    assert (clemente.criticality, clemente.visit_priority) == ("critical", "now")
    assert (maria.criticality, maria.visit_priority) == ("moderate", "soon")
    assert (agustin.criticality, agustin.visit_priority) == ("stable", "ok")
    assert clemente.priority_score > maria.priority_score > agustin.priority_score


def test_loading_twice_does_not_duplicate_anything():
    _load()
    _load()

    assert Report.objects.count() == 3
    assert Handoff.objects.count() == 1
    assert User.objects.get(email="tomas.werth@localhost").patients.count() == 0
    assert User.objects.filter(email__endswith="@localhost").count() == 3


def test_the_audio_runs_offline_and_raises_the_alert_and_the_conflict():
    _load()
    cristobal = User.objects.get(email="cristobal.tubino@localhost")
    clemente = Patient.objects.get(name="Clemente Vial")

    recording = create_recording(
        professional=cristobal,
        audio=SimpleUploadedFile(
            deploy_demo.TUBINO_AUDIO.name, deploy_demo.TUBINO_AUDIO.read_bytes(), "audio/wav"
        ),
        source=Recording.Source.UPLOAD,
        recorded_at=timezone.now(),
        patient=clemente,
    )
    transcription = Transcription.objects.create(
        recording=recording, language="spanish", model_id="cache"
    )
    transcription_services.run_transcription(transcription.id)
    transcription.refresh_from_db()
    assert transcription.text == deploy_demo.TUBINO_TEXT  # de la caché, sin Whisper
    record = ExtractedRecord.objects.get(transcription=transcription)
    extraction.run_extraction(record.id)
    report = Report.objects.get(extracted_record=record)

    assert report.profession == "kinesiologia" and report.status == Report.Status.REVIEW, (
        report.error
    )
    # 1) Alerta: el cultivo negativo no está en el informe de Cristóbal.
    (alert,) = [a for a in report.evidence_alerts if a["kind"] == "omission"]
    assert "Cultivo de aspirado traqueal" in alert["message"] and "negativo" in alert["message"]
    # 2) Conflicto claro con el informe de Tomás: RASS -4 frente a RASS -1.
    for point in report_services.pending_review_items(report):
        report_services.review_item(report, point.id)
    report = report_services.validate_report(report)
    assert report.consolidation == Report.Consolidation.RECONCILING
    (conflict,) = report.reconciliations.get().conflicts.all()
    assert conflict.section == "escalas" and "RASS" in conflict.label
    assert {conflict.side_a["value"], conflict.side_b["value"]} == {"-4", "-1"}
    assert conflict.side_a["authorName"] == "Tomás Werth"
    assert ConsolidatedVersion.objects.get(patient=clemente, is_current=True).version == 1
