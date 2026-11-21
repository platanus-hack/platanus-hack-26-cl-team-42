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
        patient_reference="Box 7",
        profession="kinesiologia",
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


def test_template_is_chosen_from_the_recording_profession(transcription):
    record = extraction.request_extraction(transcription)

    assert record.template.slug == "kinesiologia_uci"


def test_template_can_be_overridden_explicitly(transcription):
    record = extraction.request_extraction(transcription, "medico_uci")

    assert record.template.slug == "medico_uci"


def test_request_without_profession_or_template_fails(transcription):
    transcription.recording.profession = ""
    transcription.recording.save()

    with pytest.raises(extraction.ExtractionError):
        extraction.request_extraction(transcription)


def test_automatic_extraction_needs_a_profession(transcription):
    transcription.recording.profession = ""
    transcription.recording.save()

    assert extraction.request_automatic_extraction(transcription) is None
    assert not ExtractedRecord.objects.exists()


def test_finishing_a_transcription_queues_the_extraction(monkeypatch, transcription):
    from apps.transcription import services

    transcription.status = Transcription.Status.PENDING
    transcription.text = ""
    transcription.save()
    monkeypatch.setattr(services, "transcribe", lambda audio: "Kinesiología: movilización pasiva.")

    services.run_transcription(transcription.id)

    assert ExtractedRecord.objects.get().template.slug == "kinesiologia_uci"


def test_extraction_prompt_includes_recording_metadata(monkeypatch, transcription):
    model = _use_model(monkeypatch, [json.dumps(_valid_record())])
    record = extraction.request_extraction(transcription, "medico_uci")

    extraction.run_extraction(record.id)

    prompt = model.calls[0][1].content
    assert "Paciente / cama: Box 7" in prompt
    assert "Kinesiología" not in prompt


def test_api_extract_uses_the_recording_profession(monkeypatch, client, transcription):
    response = client.post(
        f"{API_URL}/transcripts/{transcription.id}/extract",
        data={},
        content_type="application/json",
    )

    assert response.status_code == 202
    assert response.json()["templateSlug"] == "kinesiologia_uci"


class StreamingModel(FakeModel):
    streams = True

    def __init__(self, reply: str, on_partial):
        super().__init__([reply])
        self.on_partial = on_partial

    def complete(self, messages, on_delta=None):
        reply = super().complete(messages)
        on_delta(reply[: len(reply) // 2])
        self.on_partial()
        return reply


def test_partial_record_is_saved_while_the_model_is_still_writing(monkeypatch, transcription):
    monkeypatch.setattr(extraction, "PROGRESS_INTERVAL_SECONDS", 0)
    record = extraction.request_extraction(transcription, "medico_uci")
    seen: list[dict | None] = []
    model = StreamingModel(
        json.dumps(_valid_record()), lambda: seen.append(ExtractedRecord.objects.get().data)
    )
    monkeypatch.setattr(extraction, "_extraction_model", lambda: model)

    extraction.run_extraction(record.id)

    assert seen[0], "el registro parcial debía guardarse antes de terminar"
    assert len(seen[0]) < len(_valid_record())
    assert ExtractedRecord.objects.get().data == _valid_record()


def test_requesting_again_while_one_is_running_does_not_queue_another(transcription):
    first = extraction.request_extraction(transcription)
    first.status = ExtractedRecord.Status.PROCESSING
    first.save()

    second = extraction.request_extraction(transcription)

    assert second.id == first.id
    assert second.status == ExtractedRecord.Status.PROCESSING


def test_stale_in_progress_record_is_requeued(transcription):
    from datetime import timedelta

    from django.utils import timezone

    first = extraction.request_extraction(transcription)
    ExtractedRecord.objects.filter(pk=first.pk).update(
        status=ExtractedRecord.Status.PROCESSING, updated_at=timezone.now() - timedelta(hours=1)
    )

    second = extraction.request_extraction(transcription)

    assert second.status == ExtractedRecord.Status.PENDING


@pytest.fixture()
def done_record(transcription):
    record = extraction.request_extraction(transcription, "medico_uci")
    record.status = ExtractedRecord.Status.DONE
    record.data = _valid_record()
    record.save()
    return record


def test_section_is_completed_with_written_information(monkeypatch, done_record):
    model = _use_model(monkeypatch, [json.dumps({"resumen_24h": "Evolución estable."})])

    extraction.request_section_update(done_record, "resumen_24h", "Evolución estable.")
    done_record.refresh_from_db()
    assert done_record.status == ExtractedRecord.Status.PROCESSING

    assert extraction.run_section_update(done_record.id, "resumen_24h", "Evolución estable.", "")

    done_record.refresh_from_db()
    assert done_record.status == ExtractedRecord.Status.DONE
    assert done_record.data["resumen_24h"] == "Evolución estable."
    assert done_record.data["metadatos"] == _valid_record()["metadatos"]
    assert "Evolución estable." in model.calls[0][1].content


def test_section_is_completed_with_another_audio(monkeypatch, done_record):
    model = _use_model(monkeypatch, [json.dumps({"resumen_24h": "Dicho en audio."})])
    monkeypatch.setattr(extraction, "_transcribe_stored_audio", lambda name: "texto del audio")
    audio = SimpleUploadedFile("complemento.wav", b"x", "audio/wav")

    extraction.request_section_update(done_record, "resumen_24h", "", audio)
    audio_name = _stored_audio_name(done_record)
    extraction.run_section_update(done_record.id, "resumen_24h", "", audio_name)

    done_record.refresh_from_db()
    assert done_record.data["resumen_24h"] == "Dicho en audio."
    assert "texto del audio" in model.calls[0][1].content
    from django.core.files.storage import default_storage

    assert not default_storage.exists(audio_name), "el audio temporal debía borrarse"


def _stored_audio_name(record) -> str:
    from django.core.files.storage import default_storage

    _, files = default_storage.listdir("complements")
    return next(f"complements/{name}" for name in files if name.startswith(f"{record.id}-"))


def test_failed_section_update_keeps_the_record_and_reports_the_error(monkeypatch, done_record):
    _use_model(monkeypatch, ["no es json", "{}"])
    extraction.request_section_update(done_record, "resumen_24h", "algo")

    extraction.run_section_update(done_record.id, "resumen_24h", "algo", "")

    done_record.refresh_from_db()
    assert done_record.status == ExtractedRecord.Status.DONE
    assert done_record.data == _valid_record()
    assert "No se pudo incorporar" in done_record.error


def test_section_update_rejects_unknown_sections_and_empty_input(done_record):
    with pytest.raises(extraction.ExtractionError):
        extraction.request_section_update(done_record, "inexistente", "algo")
    with pytest.raises(extraction.ExtractionError):
        extraction.request_section_update(done_record, "resumen_24h", "   ")


def test_api_complement_with_text(monkeypatch, client, done_record):
    response = client.post(
        f"{API_URL}/extractions/{done_record.id}/complement",
        data={"section": "resumen_24h", "text": "Estable."},
    )

    assert response.status_code == 202, response.content
    assert response.json()["status"] == "processing"


def test_api_complement_with_audio_and_ownership(monkeypatch, client, done_record):
    response = client.post(
        f"{API_URL}/extractions/{done_record.id}/complement",
        data={
            "section": "resumen_24h",
            "audio": SimpleUploadedFile("c.webm", b"x", "audio/webm;codecs=opus"),
        },
    )
    assert response.status_code == 202, response.content

    from django.core.files.storage import default_storage

    default_storage.delete(_stored_audio_name(done_record))

    other = User.objects.create_user(email="otro2@example.com", password="pw")
    done_record.transcription.recording.professional = other
    done_record.transcription.recording.save()
    denied = client.post(
        f"{API_URL}/extractions/{done_record.id}/complement",
        data={"section": "resumen_24h", "text": "x"},
    )
    assert denied.status_code == 404


def test_empty_values_never_overwrite_existing_information():
    old = {"cama": "7", "fecha": "2026-11-21", "turno": None, "items": [1, 2]}
    new = {"cama": "7", "fecha": None, "turno": "noche", "items": []}

    assert extraction._keep_existing(old, new) == {
        "cama": "7",
        "fecha": "2026-11-21",
        "turno": "noche",
        "items": [1, 2],
    }


def test_section_update_keeps_what_the_model_dropped(monkeypatch, done_record):
    dropped = {**_valid_record()["metadatos"], "cama": None}
    _use_model(monkeypatch, [json.dumps({"metadatos": dropped})])
    extraction.request_section_update(done_record, "metadatos", "Turno de noche.")

    extraction.run_section_update(done_record.id, "metadatos", "Turno de noche.", "")

    done_record.refresh_from_db()
    assert done_record.data["metadatos"]["cama"] == _valid_record()["metadatos"]["cama"]
