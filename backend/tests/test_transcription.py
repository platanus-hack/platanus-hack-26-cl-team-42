"""Unit tests for the transcription module and its link with recordings."""

import hashlib
import io
import json
import subprocess
from io import StringIO
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pytest
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.test import Client

from apps.recordings.models import Recording
from apps.recordings.services import create_recording
from apps.transcription import services, tasks
from apps.transcription.models import Transcription
from apps.transcription.services import request_transcription, run_transcription

SAMPLE_AUDIO = Path(services.__file__).parent / "samples" / "ejemplo.wav"
API = f"/{settings.URL_PREFIX}/api"
User = get_user_model()


class FakeTranscriber:
    def __init__(self, text: str):
        self.text = text
        self.calls: list[tuple[dict, dict]] = []

    def __call__(self, audio: dict, generate_kwargs: dict, **options) -> dict:
        self.calls.append((audio, generate_kwargs))
        return {"text": f"  {self.text}  "}


class FailingTranscriber:
    def __call__(self, audio: dict, generate_kwargs: dict, **options) -> dict:
        raise RuntimeError("modelo caído")


@pytest.fixture(autouse=True)
def _media_root(settings, tmp_path):
    settings.MEDIA_ROOT = str(tmp_path)


@pytest.fixture()
def doctor(db):
    return User.objects.create_user(email="doctor@example.com", password="pw", name="Dra. Demo")


@pytest.fixture()
def client_for(db):
    def make(user):
        client = Client()
        client.force_login(user)
        return client

    return make


def _recording(professional, content=None, content_type="audio/wav", name="dictado.wav"):
    data = SAMPLE_AUDIO.read_bytes() if content is None else content
    return create_recording(
        professional=professional,
        audio=SimpleUploadedFile(name, data, content_type=content_type),
        source=Recording.Source.IN_APP,
        patient_reference="Cama 4",
    )


def _pending(professional, **kwargs) -> Transcription:
    with patch.object(tasks.transcribe_recording, "delay"):
        return request_transcription(_recording(professional, **kwargs))


@pytest.mark.django_db
def test_saving_a_recording_queues_its_transcription(
    doctor, client_for, django_capture_on_commit_callbacks
):
    upload = SimpleUploadedFile("dictado.webm", b"opus", content_type="audio/webm;codecs=opus")

    with (
        patch.object(tasks.transcribe_recording, "delay") as delay,
        django_capture_on_commit_callbacks(execute=True),
    ):
        response = client_for(doctor).post(
            f"{API}/recordings", {"audio": upload, "source": "in_app"}
        )

    assert response.status_code == 201, response.content
    transcription = Transcription.objects.get(recording_id=response.json()["id"])
    assert transcription.status == Transcription.Status.PENDING
    delay.assert_called_once_with(transcription.id)


@pytest.mark.django_db
def test_run_transcription_saves_text_and_keeps_audio(doctor):
    transcription = _pending(doctor)
    fake = FakeTranscriber("Hola mundo")

    with patch.object(services, "_get_transcriber", return_value=fake):
        assert run_transcription(transcription.id) == Transcription.Status.DONE

    transcription.refresh_from_db()
    assert transcription.text == "Hola mundo"
    assert transcription.error == ""
    assert transcription.recording.audio.storage.exists(transcription.recording.audio.name)
    [(sent_audio, generate_kwargs)] = fake.calls
    assert sent_audio["sampling_rate"] == 16000
    assert len(sent_audio["raw"]) > 0
    assert generate_kwargs == {"language": "spanish", "task": "transcribe"}


@pytest.mark.django_db
def test_failed_transcription_is_marked_for_retry(doctor):
    transcription = _pending(doctor)

    with patch.object(services, "_get_transcriber", return_value=FailingTranscriber()):
        assert run_transcription(transcription.id) == Transcription.Status.FAILED

    transcription.refresh_from_db()
    assert transcription.error == "No se pudo transcribir el audio. Intenta nuevamente."


@pytest.mark.django_db
def test_browser_formats_are_decoded_with_ffmpeg(doctor):
    transcription = _pending(doctor, content=b"opus", content_type="audio/webm", name="d.webm")
    pcm = np.zeros(16000, dtype=np.int16).tobytes()
    fake = FakeTranscriber("convertido")
    ffmpeg_output = subprocess.CompletedProcess(args=[], returncode=0, stdout=pcm, stderr=b"")

    with (
        patch.object(services.shutil, "which", return_value="/usr/bin/ffmpeg"),
        patch.object(services.subprocess, "run", return_value=ffmpeg_output) as run,
        patch.object(services, "_get_transcriber", return_value=fake),
    ):
        run_transcription(transcription.id)

    transcription.refresh_from_db()
    assert transcription.text == "convertido"
    assert run.call_args.kwargs["input"] == b"opus"
    assert len(fake.calls[0][0]["raw"]) == 16000


@pytest.mark.django_db
def test_missing_ffmpeg_fails_with_a_clear_message(doctor):
    transcription = _pending(doctor, content=b"opus", content_type="audio/webm", name="d.webm")

    with (
        patch.object(services.shutil, "which", return_value=None),
        patch.object(services, "_get_transcriber", return_value=FakeTranscriber("x")),
    ):
        run_transcription(transcription.id)

    transcription.refresh_from_db()
    assert transcription.status == Transcription.Status.FAILED
    assert "ffmpeg" in transcription.error


@pytest.mark.django_db
def test_transcripts_are_scoped_to_their_professional(doctor, client_for):
    other = User.objects.create_user(email="other@example.com", password="pw")
    mine = _pending(doctor)
    _pending(other)

    response = client_for(doctor).get(f"{API}/transcription/transcripts")

    assert response.status_code == 200
    [item] = response.json()
    assert item["id"] == str(mine.id)
    assert item["recordingId"] == str(mine.recording_id)
    assert item["patientReference"] == "Cama 4"
    assert item["status"] == "pending"
    assert (
        client_for(other).get(f"{API}/transcription/recordings/{mine.recording_id}").status_code
        == 404
    )


@pytest.mark.django_db
def test_retry_requeues_only_failed_transcriptions(doctor, client_for):
    transcription = _pending(doctor)
    url = f"{API}/transcription/recordings/{transcription.recording_id}"
    client = client_for(doctor)

    assert client.post(url).status_code == 409

    Transcription.objects.filter(pk=transcription.pk).update(
        status=Transcription.Status.FAILED, error="falló"
    )
    with patch.object(tasks.transcribe_recording, "delay"):
        response = client.post(url)

    assert response.status_code == 202
    assert response.json()["status"] == "pending"
    assert response.json()["error"] == ""


@pytest.mark.django_db
def test_load_sample_audio_command_transcribes_for_the_user(doctor):
    stdout = StringIO()
    with patch.object(services, "_get_transcriber", return_value=FakeTranscriber("ejemplo")):
        call_command("load_sample_audio", doctor.email, stdout=stdout)

    transcription = Transcription.objects.get(recording__professional=doctor)
    assert transcription.status == Transcription.Status.DONE
    assert "ejemplo" in stdout.getvalue()


def test_known_audio_is_transcribed_from_the_cache_without_loading_whisper(tmp_path):
    audio = b"audio de demo"
    cache = tmp_path / "transcripts.json"
    digest = hashlib.sha256(audio).hexdigest()
    cache.write_text(json.dumps({digest: {"file": "demo.wav", "text": "texto conocido"}}))

    with (
        patch.object(services, "TRANSCRIPT_CACHE_PATH", cache),
        patch.object(services, "_get_transcriber") as get_transcriber,
    ):
        assert services.transcribe(io.BytesIO(audio)) == "texto conocido"

    get_transcriber.assert_not_called()


def test_unknown_audio_still_goes_through_whisper(tmp_path):
    cache = tmp_path / "transcripts.json"
    cache.write_text("{}")
    fake = FakeTranscriber("hola")

    with (
        patch.object(services, "TRANSCRIPT_CACHE_PATH", cache),
        patch.object(services, "_get_transcriber", return_value=fake),
    ):
        assert services.transcribe(SAMPLE_AUDIO) == "hola"
