"""Etapa de un dictado en proceso, para mostrarla en la bandeja «Mis pacientes»."""

from datetime import UTC, datetime

import pytest
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile

from apps.clinical_templates import services as template_services
from apps.recordings.models import Patient, Recording
from apps.transcription.inbox_services import inbox_states
from apps.transcription.models import ExtractedRecord, Report, Transcription

User = get_user_model()


@pytest.fixture()
def setup(db):
    template_services.sync_templates_from_files()
    user = User.objects.create_user(email="m@example.com", password="pw", name="Dr. X")
    patient = Patient.objects.create(name="Paciente", identifier="1-1", bed="Box 1")
    patient.assigned_to.add(user)
    recording = Recording.objects.create(
        professional=user,
        patient=patient,
        audio=SimpleUploadedFile("a.wav", b"x", "audio/wav"),
        mime_type="audio/wav",
        size_bytes=1,
        source=Recording.Source.UPLOAD,
        recorded_at=datetime(2026, 11, 20, 10, 0, tzinfo=UTC),
        profession="medico",
    )
    return user, patient, recording


def _state(user, patient):
    return inbox_states(user, [patient.id])[patient.id]


def test_the_inbox_names_the_stage_of_a_dictation_in_process(setup):
    user, patient, recording = setup

    # Sin transcripción todavía: en cola.
    state = _state(user, patient)
    assert (state.status.value, state.stage_step, state.stage_label) == ("processing", 0, "En cola")

    transcription = Transcription.objects.create(
        recording=recording, status=Transcription.Status.PENDING, language="es", model_id="w"
    )
    assert _state(user, patient).stage_step == 0

    transcription.status = Transcription.Status.PROCESSING
    transcription.save()
    state = _state(user, patient)
    assert (state.stage_step, state.stage_label) == (1, "Transcribiendo el audio")

    transcription.status = Transcription.Status.DONE
    transcription.save()
    state = _state(user, patient)
    assert (state.stage_step, state.stage_label) == (2, "Identificando la plantilla")

    record = ExtractedRecord.objects.create(
        transcription=transcription,
        template=template_services.get_active_template_for_profession("medico"),
        status=ExtractedRecord.Status.PROCESSING,
    )
    assert _state(user, patient).stage_label == "Parseando a la plantilla"

    record.status = ExtractedRecord.Status.DONE
    record.save()
    report = Report.objects.create(
        extracted_record=record,
        author=user,
        patient=patient,
        profession="medico",
        status=Report.Status.PROCESSING,
    )
    state = _state(user, patient)
    assert (state.stage_step, state.stage_label) == (3, "Homologando los conceptos")

    report.status = Report.Status.REVIEW
    report.save()
    state = _state(user, patient)
    assert (state.status.value, state.stage_step, state.stage_label) == ("review", None, None)


def test_the_patient_list_exposes_the_stage(setup):
    from django.conf import settings
    from django.test import Client

    user, _patient, recording = setup
    Transcription.objects.create(
        recording=recording, status=Transcription.Status.PROCESSING, language="es", model_id="w"
    )
    client = Client()
    client.force_login(user)

    listed = client.get(f"/{settings.URL_PREFIX}/api/patients").json()[0]

    assert listed["inboxStatus"] == "processing"
    assert (listed["processingStep"], listed["processingLabel"]) == (1, "Transcribiendo el audio")
