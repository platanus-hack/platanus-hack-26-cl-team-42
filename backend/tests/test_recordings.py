"""Unit tests for the recordings (dictados) module."""

from __future__ import annotations

from datetime import UTC, datetime
from io import StringIO

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


@pytest.mark.django_db
def test_demo_patients_are_assigned_and_loading_is_idempotent():
    from django.core.management import call_command

    from apps.recordings.services import patients_of

    user = User.objects.create_user(email="demo@example.com", password="pw")

    call_command("load_demo_patients", "demo@example.com", stdout=StringIO())
    call_command("load_demo_patients", "demo@example.com", stdout=StringIO())

    assert patients_of(user).count() == 6
    team = User.objects.get(email="enfermeria@localhost")
    assert (team.profession, patients_of(team).count()) == ("enfermeria", 1)


@pytest.mark.django_db
def test_demo_team_is_on_shift_and_the_shift_can_be_toggled():
    from django.core.management import call_command

    from apps.users import shifts

    User.objects.create_user(email="demo@example.com", password="pw")
    call_command("load_demo_patients", "demo@example.com", stdout=StringIO())
    nurse = User.objects.get(email="enfermeria@localhost")
    assert shifts.is_on_shift(nurse)

    call_command("set_demo_shift", "enfermeria@localhost", "off", stdout=StringIO())
    assert not shifts.is_on_shift(nurse)
    call_command("set_demo_shift", "enfermeria@localhost", "on", stdout=StringIO())
    assert shifts.is_on_shift(nurse)


@pytest.mark.django_db
def test_demo_scenario_builds_every_situation_offline_and_is_idempotent():
    from django.core.management import call_command

    from apps.recordings.services import patients_of
    from apps.transcription import inbox_services as inbox
    from apps.transcription import reconciliation_services as rec
    from apps.transcription.models import (
        Conflict,
        ConsolidatedVersion,
        ExternalConsult,
        Report,
        Transcription,
    )
    from apps.transcription.triage_services import triage_for
    from apps.users import shifts

    admin = User.objects.create_user(email="demo@example.com", password="pw")
    call_command("load_demo_scenario", "demo@example.com", stdout=StringIO())
    reports = Report.objects.count()
    call_command("load_demo_scenario", "demo@example.com", stdout=StringIO())
    assert Report.objects.count() == reports  # idempotente

    by_name = {p.name.split()[0]: p for p in patients_of(admin)}
    assert len(by_name) == 9
    triage = triage_for([p.id for p in by_name.values()], {p.id: None for p in by_name.values()})
    # Cada profesional tiene sus propios pacientes: no todos ven a todos.
    rojas = User.objects.get(email="medico@localhost")
    vega = User.objects.get(email="medico2@localhost")
    assert {p.name.split()[0] for p in patients_of(rojas)} == {"Marta", "Pedro", "Diego", "Sofía"}
    assert {p.name.split()[0] for p in patients_of(vega)} >= {"Elena", "Hugo", "Camila", "Tomás"}
    assert not patients_of(User.objects.get(email="especialista@localhost")).exists()

    # Crítica con varias versiones; moderada, alta y estable según su caso.
    assert triage[by_name["Marta"].id].criticality == "critical"
    assert ConsolidatedVersion.objects.filter(patient=by_name["Marta"]).count() == 2
    assert triage[by_name["Camila"].id].criticality == "high"
    assert triage[by_name["Elena"].id].criticality == "stable"
    assert triage[by_name["Sofía"].id].criticality == "unknown"

    # Estados de la bandeja: por validar y error. Ningún dictado queda «procesando» para siempre.
    states = {
        name: inbox.inbox_states(user, [by_name[name].id])[by_name[name].id].status
        for name, user in (
            ("Hugo", vega),
            ("Lucía", User.objects.get(email="kinesiologia@localhost")),
        )
    }
    assert {k: v.value for k, v in states.items()} == {"Hugo": "review", "Lucía": "failed"}
    assert not Transcription.objects.filter(status__in=["pending", "processing"]).exists()
    assert triage[by_name["Diego"].id].criticality == "high"
    assert ConsolidatedVersion.objects.filter(patient=by_name["Diego"]).count() == 1

    # Conflictos: uno resuelto con historial, uno en consenso, y el de la alergia con el caso
    # anonimizado enviado a la especialista porque EU Díaz ya está fuera de turno.
    camila = Conflict.objects.get(reconciliation__patient=by_name["Camila"])
    assert camila.status == "resolved" and camila.notes.filter(kind="note").count() == 2
    assert ConsolidatedVersion.objects.filter(patient=by_name["Camila"], reason="reconciliation")
    pedro = Conflict.objects.filter(reconciliation__patient=by_name["Pedro"])
    assert pedro.count() == 2 and all(c.status == "open" for c in pedro)
    assert any(c.proposal for c in pedro)
    assert not shifts.is_on_shift(User.objects.get(email="enfermeria2@localhost"))
    allergy = Conflict.objects.get(reconciliation__patient=by_name["Tomás"])
    assert allergy.kind == "allergy" and allergy.consults.count() == 1
    assert ExternalConsult.objects.get().consultant.email == "especialista@localhost"
    assert rec.list_external_consults(User.objects.get(email="especialista@localhost"))
    assert Report.objects.filter(patient=by_name["Hugo"], status="review").count() == 1


@pytest.mark.django_db
def test_demo_scenario_splits_the_legacy_patients_between_professionals():
    from django.core.management import call_command

    from apps.recordings.services import patients_of

    admin = User.objects.create_user(email="demo@example.com", password="pw")
    call_command("load_demo_patients", "demo@example.com", stdout=StringIO())
    call_command("load_demo_scenario", "demo@example.com", stdout=StringIO())

    def first_names(email):
        return {p.name.split()[0] for p in patients_of(User.objects.get(email=email))}

    assert {"Juan", "María", "Carlos"} <= first_names("medico@localhost")
    assert not {"Ana", "Luis", "Rosa"} & first_names("medico@localhost")
    assert {"Ana", "Luis", "Rosa"} <= first_names("medico2@localhost")
    assert "Juan" not in first_names("medico2@localhost")
    assert "Juan" in first_names("kinesiologia@localhost")  # la historia de conflictos sigue entera
    assert len(patients_of(admin)) == 15  # la cuenta de prueba ve a todos


@pytest.mark.django_db
def test_demo_scenario_loads_exams_and_a_report_with_contradictions():
    from django.core.management import call_command

    from apps.transcription.models import Evidence, Report

    User.objects.create_user(email="demo@example.com", password="pw")
    call_command("load_demo_scenario", "demo@example.com", stdout=StringIO())
    call_command("load_demo_scenario", "demo@example.com", stdout=StringIO())

    assert Evidence.objects.filter(patient__name__startswith="Elena").count() == 1  # idempotente
    hugo = Report.objects.get(patient__name__startswith="Hugo")
    assert hugo.status == "review"
    kinds = {a["id"] for a in hugo.evidence_alerts}
    # Lipasa y creatinina contradicen al informe; el potasio muy alto no se menciona.
    assert kinds == {
        "value:examenes:lipasa",
        "value:examenes:creatinina",
        "omission:examenes:potasio",
    }
