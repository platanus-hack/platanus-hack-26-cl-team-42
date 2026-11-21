"""Extracción de registros clínicos desde transcripciones: servicio y API."""

from __future__ import annotations

import json

import pytest
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client

from apps.clinical_templates import services as template_services
from apps.recordings.models import Recording
from apps.transcription import extraction_services as extraction
from apps.transcription.models import ExtractedRecord, Transcription

API_URL = f"/{settings.URL_PREFIX}/api/transcription"
User = get_user_model()


class FakeModel:
    name = "fake"

    def __init__(self, replies: list[str]):
        self.replies = list(replies)
        self.calls: list[list] = []

    def complete(self, messages):
        self.calls.append(list(messages))
        return self.replies.pop(0)


@pytest.fixture()
def user(db):
    return User.objects.create_superuser(email="medico@example.com", password="pw")


@pytest.fixture()
def client(user):
    c = Client()
    c.force_login(user)
    return c


@pytest.fixture()
def transcription(user):
    template_services.sync_templates_from_files()
    recording = Recording.objects.create(
        professional=user,
        audio=SimpleUploadedFile("a.wav", b"x", "audio/wav"),
        mime_type="audio/wav",
        size_bytes=1,
        source=Recording.Source.UPLOAD,
        recorded_at="2026-11-21T10:00:00Z",
    )
    return Transcription.objects.create(
        recording=recording,
        status=Transcription.Status.DONE,
        text="Paciente en box 7, día 3 de estadía UCI.",
        language="spanish",
        model_id="whisper",
    )


@pytest.fixture(autouse=True)
def no_celery(monkeypatch):
    monkeypatch.setattr(extraction, "_enqueue", lambda record_id: None)


def _valid_record() -> dict:
    path = template_services.examples_dir / "medico_uci.json"
    return json.loads(path.read_text(encoding="utf-8"))


def _use_model(monkeypatch, replies: list[str]) -> FakeModel:
    model = FakeModel(replies)
    monkeypatch.setattr(extraction, "_extraction_model", lambda: model)
    return model


def test_extraction_stores_valid_record(monkeypatch, transcription):
    model = _use_model(monkeypatch, [f"```json\n{json.dumps(_valid_record())}\n```"])
    record = extraction.request_extraction(transcription, "medico_uci")

    assert extraction.run_extraction(record.id) == ExtractedRecord.Status.DONE

    record.refresh_from_db()
    assert record.data == _valid_record()
    assert "box 7" in model.calls[0][1].content


@pytest.mark.django_db
def test_extraction_retries_with_validation_feedback(monkeypatch, transcription):
    invalid = _valid_record()
    del invalid["metadatos"]
    model = _use_model(monkeypatch, [json.dumps(invalid), json.dumps(_valid_record())])
    record = extraction.request_extraction(transcription, "medico_uci")

    assert extraction.run_extraction(record.id) == ExtractedRecord.Status.DONE
    assert "metadatos" in model.calls[1][-1].content


@pytest.mark.django_db
def test_extraction_fails_after_invalid_attempts(monkeypatch, transcription):
    _use_model(monkeypatch, ["no es json", "{}"])
    record = extraction.request_extraction(transcription, "medico_uci")

    assert extraction.run_extraction(record.id) == ExtractedRecord.Status.FAILED

    record.refresh_from_db()
    assert record.data is None
    assert "no produjo un registro válido" in record.error


@pytest.mark.django_db
def test_request_extraction_requires_finished_transcription(transcription):
    transcription.status = Transcription.Status.PROCESSING
    transcription.save()

    with pytest.raises(extraction.ExtractionError):
        extraction.request_extraction(transcription, "medico_uci")


@pytest.mark.django_db
def test_request_extraction_rejects_unknown_template(transcription):
    with pytest.raises(extraction.ExtractionError):
        extraction.request_extraction(transcription, "no_existe")


def test_api_extract_and_list(monkeypatch, client, transcription):
    _use_model(monkeypatch, [json.dumps(_valid_record())])

    response = client.post(
        f"{API_URL}/transcripts/{transcription.id}/extract",
        data={"template_slug": "medico_uci"},
        content_type="application/json",
    )
    assert response.status_code == 202
    assert response.json()["status"] == "pending"

    extraction.run_extraction(ExtractedRecord.objects.get().id)
    listed = client.get(f"{API_URL}/extractions").json()

    assert len(listed) == 1
    assert listed[0]["status"] == "done"
    assert listed[0]["templateSlug"] == "medico_uci"
    assert listed[0]["transcriptId"] == str(transcription.id)
    assert listed[0]["data"]["metadatos"]["cama"] == "Box 7"


def test_api_extract_conflicts_when_not_ready(client, transcription):
    transcription.status = Transcription.Status.PENDING
    transcription.save()

    response = client.post(
        f"{API_URL}/transcripts/{transcription.id}/extract",
        data={"template_slug": "medico_uci"},
        content_type="application/json",
    )

    assert response.status_code == 409


def test_api_extract_hides_other_professionals_transcripts(client, transcription):
    other = User.objects.create_user(email="otro@example.com", password="pw")
    transcription.recording.professional = other
    transcription.recording.save()

    response = client.post(
        f"{API_URL}/transcripts/{transcription.id}/extract",
        data={"template_slug": "medico_uci"},
        content_type="application/json",
    )

    assert response.status_code == 404
