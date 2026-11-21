from io import StringIO
from pathlib import Path
from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import Client

from apps.transcription import services
from apps.transcription.models import Audio, Transcription
from apps.transcription.services import ingest_audio, list_transcriptions

SAMPLE_AUDIO = Path(services.__file__).parent / "samples" / "ejemplo.wav"


class FakeTranscriber:
    def __init__(self, text: str):
        self.text = text
        self.calls: list[tuple[dict, dict]] = []

    def __call__(self, audio: dict, generate_kwargs: dict) -> dict:
        self.calls.append((audio, generate_kwargs))
        return {"text": f"  {self.text}  "}


class FailingTranscriber:
    def __call__(self, audio: dict, generate_kwargs: dict) -> dict:
        raise RuntimeError("modelo caído")


@pytest.mark.django_db
def test_ingest_audio_transcribes_links_and_clears_audio_data():
    fake = FakeTranscriber("Hola mundo")

    with patch.object(services, "_get_transcriber", return_value=fake):
        item = ingest_audio("ejemplo.wav", "audio/wav", SAMPLE_AUDIO.read_bytes())

    assert item.text == "Hola mundo"
    assert item.status == "done"
    assert item.name == "ejemplo.wav"
    audio = Audio.objects.get()
    assert audio.data is None
    assert audio.size_bytes == SAMPLE_AUDIO.stat().st_size
    assert audio.transcription.text == "Hola mundo"
    [(sent_audio, generate_kwargs)] = fake.calls
    assert sent_audio["sampling_rate"] == 16000
    assert len(sent_audio["raw"]) > 0
    assert generate_kwargs == {"language": "spanish", "task": "transcribe"}


@pytest.mark.django_db
def test_failed_transcription_keeps_audio_for_retry():
    with patch.object(services, "_get_transcriber", return_value=FailingTranscriber()):
        with pytest.raises(RuntimeError):
            ingest_audio("ejemplo.wav", "audio/wav", SAMPLE_AUDIO.read_bytes())

    audio = Audio.objects.get()
    assert audio.data is not None
    assert not Transcription.objects.exists()


@pytest.mark.django_db
def test_ingest_rejects_non_wav_audio():
    with pytest.raises(ValueError):
        ingest_audio("nota.mp3", "audio/mpeg", b"no es un wav")


@pytest.mark.django_db
def test_list_transcriptions_returns_metadata_and_text():
    with patch.object(services, "_get_transcriber", return_value=FakeTranscriber("texto")):
        ingest_audio("ejemplo.wav", "audio/wav", SAMPLE_AUDIO.read_bytes())

    [item] = list_transcriptions()

    assert item.name == "ejemplo.wav"
    assert item.recordingId == str(Audio.objects.get().id)
    assert item.text == "texto"


@pytest.mark.django_db
def test_load_sample_audio_command_is_idempotent():
    with patch.object(services, "_get_transcriber", return_value=FakeTranscriber("ejemplo")):
        call_command("load_sample_audio", stdout=StringIO())
        call_command("load_sample_audio", stdout=StringIO())

    assert Transcription.objects.count() == 1


@pytest.mark.django_db
def test_upload_endpoint_transcribes_audio(settings):
    user = get_user_model().objects.create_user(email="test@example.com", password="pw")
    client = Client()
    client.force_login(user)
    upload = SAMPLE_AUDIO.open("rb")

    with patch.object(services, "_get_transcriber", return_value=FakeTranscriber("subido")):
        response = client.post(
            f"/{settings.URL_PREFIX}/api/transcription/audios",
            {"file": upload},
        )

    assert response.status_code == 201
    assert response.json()["text"] == "subido"
    assert response.json()["name"] == "ejemplo.wav"


@pytest.mark.django_db
def test_upload_endpoint_rejects_non_wav(settings):
    user = get_user_model().objects.create_user(email="test2@example.com", password="pw")
    client = Client()
    client.force_login(user)
    upload = StringIO("no es audio")
    upload.name = "nota.wav"

    response = client.post(f"/{settings.URL_PREFIX}/api/transcription/audios", {"file": upload})

    assert response.status_code == 400


@pytest.mark.django_db
def test_transcripts_endpoint_lists_transcriptions(settings):
    with patch.object(services, "_get_transcriber", return_value=FakeTranscriber("lista")):
        ingest_audio("ejemplo.wav", "audio/wav", SAMPLE_AUDIO.read_bytes())
    user = get_user_model().objects.create_user(email="test3@example.com", password="pw")
    client = Client()
    client.force_login(user)

    response = client.get(f"/{settings.URL_PREFIX}/api/transcription/transcripts")

    assert response.status_code == 200
    assert [item["text"] for item in response.json()] == ["lista"]
