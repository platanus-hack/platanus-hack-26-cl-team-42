"""Unit tests for the recordings (dictados) module."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client

from apps.recordings.models import Recording

URL = f"/{settings.URL_PREFIX}/api/recordings"
User = get_user_model()


@pytest.fixture(autouse=True)
def _media_root(settings, tmp_path):
    settings.MEDIA_ROOT = str(tmp_path)


@pytest.fixture()
def nurse(db):
    return User.objects.create_user(email="nurse@example.com", password="pw", name="Enfermera Demo")


@pytest.fixture()
def client_for(db):
    def make(user):
        c = Client()
        c.force_login(user)
        return c

    return make


def _audio(content=b"fake-opus-bytes", content_type="audio/webm;codecs=opus", name="dictado.webm"):
    return SimpleUploadedFile(name, content, content_type=content_type)


def _upload(client, **data):
    payload = {"audio": data.pop("audio", _audio()), "source": "in_app", **data}
    return client.post(URL, data=payload)


@pytest.mark.django_db
def test_upload_creates_recording_owned_by_user(nurse, client_for):
    response = _upload(
        client_for(nurse),
        duration_seconds="12.5",
        patient_reference="Cama 4",
        recorded_at="2025-03-01T10:00:00Z",
    )

    assert response.status_code == 201, response.content
    body = response.json()
    assert body["professional_name"] == "Enfermera Demo"
    assert body["mime_type"] == "audio/webm"
    assert body["duration_seconds"] == 12.5
    assert body["patient_reference"] == "Cama 4"
    recording = Recording.objects.get(pk=body["id"])
    assert recording.professional == nurse
    assert recording.audio.name == f"recordings/{nurse.pk}/{recording.pk}.webm"


@pytest.mark.django_db
def test_rejects_non_audio_files(nurse, client_for):
    response = _upload(
        client_for(nurse), audio=_audio(content_type="application/pdf", name="x.pdf")
    )
    assert response.status_code == 400
    assert not Recording.objects.exists()


@pytest.mark.django_db
def test_rejects_empty_audio(nurse, client_for):
    response = _upload(client_for(nurse), audio=_audio(content=b""))
    assert response.status_code == 400


@pytest.mark.django_db
def test_list_and_audio_are_scoped_to_owner(nurse, client_for):
    other = User.objects.create_user(email="kine@example.com", password="pw")
    recording_id = _upload(client_for(nurse)).json()["id"]

    other_client = client_for(other)
    assert other_client.get(URL).json() == []
    assert other_client.get(f"{URL}/{recording_id}/audio").status_code == 404

    own = client_for(nurse)
    assert [r["id"] for r in own.get(URL).json()] == [recording_id]
    audio = own.get(f"{URL}/{recording_id}/audio")
    assert audio.status_code == 200
    assert audio["Content-Type"] == "audio/webm"
    assert b"".join(audio.streaming_content) == b"fake-opus-bytes"


@pytest.mark.django_db
def test_delete_removes_row_and_file(nurse, client_for, django_capture_on_commit_callbacks):
    client = client_for(nurse)
    recording_id = _upload(client).json()["id"]
    recording = Recording.objects.get(pk=recording_id)
    storage, name = recording.audio.storage, recording.audio.name

    with django_capture_on_commit_callbacks(execute=True):
        response = client.delete(f"{URL}/{recording_id}")

    assert response.status_code == 204
    assert not Recording.objects.exists()
    assert not storage.exists(name)


def test_requires_authentication(db):
    assert Client().get(URL).status_code == 401


@pytest.mark.django_db
def test_recording_name_and_profession_come_from_the_account():
    from apps.recordings.services import create_recording

    user = User.objects.create_user(email="k@example.com", password="pw", name="Klgo. Muñoz")
    user.profession = "kinesiologia"
    user.save()

    recording = create_recording(
        professional=user,
        audio=SimpleUploadedFile("a.wav", b"x", content_type="audio/wav"),
        source=Recording.Source.IN_APP,
        recorded_at=datetime(2026, 1, 21, 13, 30, tzinfo=UTC),
    )

    assert recording.profession == "kinesiologia"
    assert recording.name.startswith("Klgo. Muñoz · Kinesiología · 21-01-2026")


def test_profession_is_read_from_the_file_name():
    from apps.recordings.services import profession_from_name

    assert profession_from_name("Dr. Rojas - Médico UCI - 18-11-2026 09-30.wav") == "medico"
    assert (
        profession_from_name("Klgo. Muñoz - Kinesiología - 18-11-2026 12-00.wav") == "kinesiologia"
    )
    assert profession_from_name("EU Soto - Enfermería - 18-11-2026 11-00.wav") == "enfermeria"
    assert profession_from_name("TENS Pérez - TENS - 18-11-2026 15-00.wav") == "tens"
    assert profession_from_name("Dra. Fuentes - Especialista - 18-11-2026.wav") == "especialista"
    assert profession_from_name("dictado.webm") == ""
