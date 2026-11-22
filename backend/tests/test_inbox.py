"""Bandeja «Mis pacientes»: solo los asignados y qué necesita cada uno del profesional."""

from __future__ import annotations

from datetime import timedelta

import pytest
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client
from django.utils import timezone

from apps.clinical_templates import services as template_services
from apps.recordings.models import Patient, Recording
from apps.transcription.models import ExtractedRecord, Report, Transcription

URL = f"/{settings.URL_PREFIX}/api/patients"
User = get_user_model()


@pytest.fixture(autouse=True)
def _media_root(settings, tmp_path):
    settings.MEDIA_ROOT = str(tmp_path)


@pytest.fixture()
def nurse(db):
    return User.objects.create_user(email="nurse@example.com", password="pw", name="Enfermera")


@pytest.fixture()
def patient(nurse):
    patient = Patient.objects.create(name="Juan Pérez", identifier="1-9", bed="Box 7")
    patient.assigned_to.add(nurse)
    return patient


def test_lists_only_assigned_patients(nurse, patient):
    Patient.objects.create(name="De otro", identifier="2-7")

    body = _list(nurse)

    assert [item["name"] for item in body] == ["Juan Pérez"]
    assert body[0]["inboxStatus"] == "up_to_date"
    assert body[0]["lastDictationAt"] is None


def test_recordings_are_only_accepted_for_assigned_patients(nurse):
    other = Patient.objects.create(name="De otro", identifier="2-7")
    response = _client(nurse).post(
        f"/{settings.URL_PREFIX}/api/recordings",
        data={
            "audio": SimpleUploadedFile("a.webm", b"x", "audio/webm"),
            "source": "in_app",
            "recorded_at": "2026-11-21T10:00:00Z",
            "patient_id": other.id,
        },
    )

    assert response.status_code == 404
    assert not Recording.objects.exists()


def test_recording_without_transcription_is_processing(nurse, patient):
    recording = _recording(nurse, patient)

    item = _list(nurse)[0]

    assert item["inboxStatus"] == "processing"
    assert item["lastDictationAt"] is not None
    assert item["retryRecordingId"] is None
    assert recording.recorded_at.isoformat().startswith(item["lastDictationAt"][:19])


def test_failed_transcription_can_be_retried(nurse, patient):
    recording = _recording(nurse, patient)
    Transcription.objects.create(recording=recording, status=Transcription.Status.FAILED)

    item = _list(nurse)[0]

    assert item["inboxStatus"] == "failed"
    assert item["retryRecordingId"] == str(recording.id)


def test_own_report_to_validate_comes_first(nurse, patient):
    _report(nurse, patient, Report.Status.REVIEW)

    assert _list(nurse)[0]["inboxStatus"] == "review"


def test_validated_report_is_up_to_date(nurse, patient):
    _report(nurse, patient, Report.Status.DONE)

    assert _list(nurse)[0]["inboxStatus"] == "up_to_date"


def test_others_pending_work_does_not_need_my_action(nurse, patient):
    colleague = User.objects.create_user(email="kine@example.com", password="pw")
    patient.assigned_to.add(colleague)
    _report(colleague, patient, Report.Status.REVIEW)

    item = _list(nurse)[0]

    assert item["inboxStatus"] == "up_to_date"
    assert item["lastDictationAt"] is not None


def test_transcription_that_never_gets_a_record_is_reported_as_failed(nurse, patient):
    transcription = Transcription.objects.create(
        recording=_recording(nurse, patient), status=Transcription.Status.DONE
    )

    assert _list(nurse)[0]["inboxStatus"] == "processing"

    Transcription.objects.filter(pk=transcription.pk).update(
        updated_at=timezone.now() - timedelta(minutes=5)
    )
    item = _list(nurse)[0]
    assert item["inboxStatus"] == "failed"
    assert item["retryRecordingId"] is None


def _client(user) -> Client:
    client = Client()
    client.force_login(user)
    return client


def _list(user) -> list[dict]:
    response = _client(user).get(URL)
    assert response.status_code == 200
    return response.json()


def _recording(user, patient) -> Recording:
    return Recording.objects.create(
        professional=user,
        patient=patient,
        patient_reference=patient.reference,
        audio=SimpleUploadedFile("a.wav", b"x", "audio/wav"),
        mime_type="audio/wav",
        size_bytes=1,
        source=Recording.Source.UPLOAD,
        recorded_at=timezone.now(),
        profession="medico",
    )


def _report(user, patient, status) -> Report:
    template_services.sync_templates_from_files()
    transcription = Transcription.objects.create(
        recording=_recording(user, patient), status=Transcription.Status.DONE
    )
    record = ExtractedRecord.objects.create(
        transcription=transcription,
        template=template_services.get_active_template("medico_uci"),
        status=ExtractedRecord.Status.DONE,
        data={},
    )
    return Report.objects.create(
        extracted_record=record, author=user, patient=patient, profession="medico", status=status
    )
