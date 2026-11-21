"""Pipeline automático: identificación de plantilla, caché, homologación e informes."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client

from apps.clinical_templates import services as template_services
from apps.recordings.models import Recording
from apps.transcription import extraction_services as extraction
from apps.transcription import homologation_services as homologation
from apps.transcription.models import ConceptMapping, ExtractedRecord, Report, Transcription

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


@pytest.fixture(autouse=True)
def no_celery(monkeypatch):
    monkeypatch.setattr(extraction, "_enqueue", lambda record_id: None)


@pytest.fixture(autouse=True)
def seeded_templates(db):
    template_services.sync_templates_from_files()


@pytest.fixture()
def user(db):
    return User.objects.create_superuser(
        email="klgo@example.com", password="pw", name="Klgo. Muñoz"
    )


def _use_model(monkeypatch, replies: list[str]) -> FakeModel:
    model = FakeModel(replies)
    monkeypatch.setattr(extraction, "_extraction_model", lambda: model)
    return model


def _transcription(user, text="Evolución del paciente.", profession="", patient="Box 7"):
    recording = Recording.objects.create(
        professional=user,
        audio=SimpleUploadedFile("a.wav", b"x", "audio/wav"),
        mime_type="audio/wav",
        size_bytes=1,
        source=Recording.Source.UPLOAD,
        recorded_at="2026-11-21T10:00:00Z",
        patient_reference=patient,
        profession=profession,
    )
    return Transcription.objects.create(
        recording=recording,
        status=Transcription.Status.DONE,
        text=text,
        language="spanish",
        model_id="whisper",
    )


def _medico_record() -> dict:
    path = template_services.examples_dir / "medico_uci.json"
    return json.loads(path.read_text(encoding="utf-8"))


def _done_record(user, **kwargs) -> ExtractedRecord:
    transcription = _transcription(user, profession="medico", **kwargs)
    template = template_services.get_active_template("medico_uci")
    return ExtractedRecord.objects.create(
        transcription=transcription,
        template=template,
        status=ExtractedRecord.Status.DONE,
        data=_medico_record(),
    )


def test_profession_is_identified_by_the_model_and_cached(monkeypatch, user):
    model = _use_model(monkeypatch, ['{"profesion": "kinesiologia"}'])
    transcription = _transcription(user, text="Aspiración de secreciones y vibropresiones.")

    assert extraction.identify_profession(transcription) == "kinesiologia"
    assert extraction.identify_profession(transcription) == "kinesiologia"
    assert len(model.calls) == 1


def test_profession_falls_back_to_keywords_when_the_model_fails(monkeypatch, user):
    _use_model(monkeypatch, ["respuesta sin json"])
    transcription = _transcription(user, text="Interconsulta de infectología por neumonía.")

    assert extraction.identify_profession(transcription) == "especialista"


def test_automatic_extraction_identifies_the_template_without_a_profession(monkeypatch, user):
    _use_model(monkeypatch, ['{"profesion": "enfermeria"}'])
    transcription = _transcription(user)

    record = extraction.request_automatic_extraction(transcription)

    assert record.template.slug == "enfermeria_uci"
    transcription.recording.refresh_from_db()
    assert transcription.recording.profession == "enfermeria"


def test_extraction_is_cached_between_runs(monkeypatch, user):
    model = _use_model(monkeypatch, [json.dumps(_medico_record())])
    transcription = _transcription(user, profession="medico")

    first = extraction.request_extraction(transcription)
    extraction.run_extraction(first.id)
    second = extraction.request_extraction(transcription)  # sin más respuestas del modelo
    assert extraction.run_extraction(second.id) == ExtractedRecord.Status.DONE

    second.refresh_from_db()
    extraction_calls = [c for c in model.calls if "Términos a unificar" not in c[-1].content]
    assert len(extraction_calls) == 1
    # Lo cacheado se reutiliza tal cual, salvo la hora, que es la de este dictado.
    expected = _medico_record()
    expected["metadatos"]["fecha_hora_registro"] = "2026-11-21T10:00:00+00:00"
    assert second.data == expected


def test_homologation_unifies_known_terms_without_the_model(monkeypatch, user):
    model = _use_model(monkeypatch, [])
    data = {
        "metadatos": {"cama": "Box 7"},
        "drogas_infusion": [{"farmaco": "norepinefrina"}, {"farmaco": "Propofol"}],
        "dispositivos_invasivos": [{"tipo": "CVC"}, {"tipo": "vía central"}],
        "soporte": {"soporte": "VMI"},
    }

    result = homologation.homologate(data)

    assert result.data["drogas_infusion"][0]["farmaco"] == "Noradrenalina"
    assert [d["tipo"] for d in result.data["dispositivos_invasivos"]] == [
        "Catéter venoso central"
    ] * 2
    assert result.data["soporte"]["soporte"] == "Ventilación mecánica invasiva"
    assert result.data["metadatos"] == {"cama": "Box 7"}
    assert model.calls == []
    changed = {e["original"] for e in result.entries if e["changed"]}
    assert changed == {"norepinefrina", "CVC", "vía central", "VMI"}


def test_homologation_learns_unknown_terms_from_the_model(monkeypatch, user):
    model = _use_model(monkeypatch, [json.dumps({"conceptos": {"gentamicina ev": "Gentamicina"}})])
    data = {"medicamentos": [{"nombre": "gentamicina ev"}]}
    progress: list[int] = []

    first = homologation.homologate(data, "medico", lambda entries: progress.append(len(entries)))
    second = homologation.homologate(data, "medico")

    assert first.data["medicamentos"][0]["nombre"] == "Gentamicina"
    assert first.entries[0]["source"] == "model"
    mapping = ConceptMapping.objects.get(original_term="gentamicina ev")
    assert mapping.status == ConceptMapping.Status.PENDING
    assert second.entries[0]["source"] == "dictionary"
    assert len(model.calls) == 1


def test_homologation_keeps_terms_when_the_model_is_unavailable(monkeypatch, user):
    _use_model(monkeypatch, ["no es json"])

    result = homologation.homologate({"medicamentos": [{"nombre": "xyzmicina"}]})

    assert result.data["medicamentos"][0]["nombre"] == "xyzmicina"
    assert result.entries[0]["source"] == "unresolved"


def test_report_is_generated_after_extraction_with_author_and_order(monkeypatch, user):
    _use_model(monkeypatch, [json.dumps(_medico_record())])
    transcription = _transcription(user, profession="medico")
    record = extraction.request_extraction(transcription)

    extraction.run_extraction(record.id)

    report = record.report
    assert report.status == Report.Status.REVIEW
    assert (report.author, report.profession, report.sequence) == (user, "medico", 1)
    assert report.data["drogas_infusion"][0]["farmaco"] == "Noradrenalina"
    assert report.homologations


def test_reports_are_numbered_per_patient_and_profession(monkeypatch, user):
    from apps.transcription import report_services

    first = _done_record(user, patient="Box 7")
    second = _done_record(user, patient="Box 7")
    other_patient = _done_record(user, patient="Box 9")

    numbers = [report_services.generate_report(r).sequence for r in (first, second, other_patient)]

    assert numbers == [1, 2, 1]
    # Regenerar el informe de uno ya existente no cambia su número.
    assert report_services.generate_report(first).sequence == 1


def test_api_exposes_pipeline_reports_and_concepts(monkeypatch, user):
    from apps.transcription import report_services

    record = _done_record(user)
    report_services.generate_report(record)
    client = Client()
    client.force_login(user)
    recording_id = record.transcription.recording_id

    pipeline = client.get(f"{API_URL}/recordings/{recording_id}/pipeline").json()
    reports = client.get(f"{API_URL}/reports").json()
    concepts = client.get(f"{API_URL}/concepts").json()

    assert pipeline["transcription"]["status"] == "done"
    assert pipeline["extraction"]["status"] == "done"
    assert pipeline["report"]["sequence"] == 1
    assert pipeline["report"]["authorName"] == "Klgo. Muñoz"
    assert [r["id"] for r in reports] == [pipeline["report"]["id"]]
    assert client.get(f"{API_URL}/reports/{reports[0]['id']}").status_code == 200
    assert any(c["sourceTerm"] == "norepinefrina" for c in concepts)


def test_reports_are_private_to_their_author(user):
    from apps.transcription import report_services

    report = report_services.generate_report(_done_record(user))
    stranger = User.objects.create_user(email="otro@example.com", password="pw")
    client = Client()
    client.force_login(stranger)

    assert client.get(f"{API_URL}/reports").json() == []
    assert client.get(f"{API_URL}/reports/{report.id}").status_code == 404


def test_known_sample_audio_brings_its_profession(user):
    audio = (
        Path(__file__).parents[2]
        / "sample_audios"
        / "Klgo. Muñoz - Kinesiología - 18-11-2026 12-00.wav"
    )
    transcription = _transcription(user)
    transcription.recording.audio.save(
        "k.wav", SimpleUploadedFile("k.wav", audio.read_bytes()), save=True
    )

    assert extraction.identify_profession(transcription) == "kinesiologia"


# --- pacientes, visibilidad, resumen y asistente ---------------------------------------


def _patient(*professionals, name="Juan Pérez", identifier="12.345.678-9", bed="Cama 7"):
    from apps.recordings.models import Patient

    patient = Patient.objects.create(name=name, identifier=identifier, bed=bed)
    patient.assigned_to.add(*professionals)
    return patient


def _report_for(author, patient, profession="medico", data=None, validated=True):
    """Informe terminado de ``author`` sobre ``patient`` (sin pasar por el modelo)."""
    transcription = _transcription(author, profession=profession, patient=patient.reference)
    recording = transcription.recording
    recording.patient = patient
    recording.save()
    template = template_services.get_active_template_for_profession(profession)
    record = ExtractedRecord.objects.create(
        transcription=transcription,
        template=template,
        status=ExtractedRecord.Status.DONE,
        data=data or _medico_record(),
    )
    from apps.transcription import report_services

    report = report_services.generate_report(record)
    if validated:
        report.validated_sections = [t.id for t in report_services.topics_of(report)]
        report.save()
        report_services.validate_report(report)
    return report


def test_patients_cannot_be_created_from_the_app(user):
    client = Client()
    client.force_login(user)

    response = client.post(
        f"/{settings.URL_PREFIX}/api/patients",
        {"name": "Nuevo"},
        content_type="application/json",
    )

    assert response.status_code in (404, 405)


def test_a_patient_is_transferred_to_another_user(user):
    from apps.recordings import services as recording_services

    receiver = User.objects.create_user(email="rec@example.com", password="pw")
    patient = _patient(user)
    api = f"/{settings.URL_PREFIX}/api/patients"
    mine, theirs = Client(), Client()
    mine.force_login(user)
    theirs.force_login(receiver)

    # Quien no tiene al paciente no puede traspasarlo.
    assert (
        theirs.post(
            f"{api}/{patient.id}/transfer",
            {"to_email": "klgo@example.com"},
            content_type="application/json",
        ).status_code
        == 404
    )
    response = mine.post(
        f"{api}/{patient.id}/transfer",
        {"to_email": "REC@example.com"},
        content_type="application/json",
    )

    assert response.status_code == 200, response.content
    assert set(patient.assigned_to.all()) == {receiver}
    assert recording_services.patients_of(user).count() == 0
    assert (
        mine.post(
            f"{api}/{patient.id}/transfer",
            {"to_email": "rec@example.com"},
            content_type="application/json",
        ).status_code
        == 404
    )


def test_recording_requires_an_assigned_patient(user):
    from apps.recordings import services as recording_services

    stranger = User.objects.create_user(email="x@example.com", password="pw")
    patient = _patient(user)
    audio = SimpleUploadedFile("a.wav", b"x", content_type="audio/wav")

    with pytest.raises(recording_services.RecordingError):
        recording_services.create_recording(
            professional=stranger, audio=audio, source="in_app", patient=patient
        )
    recording = recording_services.create_recording(
        professional=user,
        audio=SimpleUploadedFile("a.wav", b"x", content_type="audio/wav"),
        source="in_app",
        patient=patient,
    )
    assert recording.patient_reference == "Juan Pérez (12.345.678-9) · Cama 7"


def test_professionals_share_the_reports_of_their_patients(user):
    other = User.objects.create_user(email="med@example.com", password="pw", name="Dr. Rojas")
    outsider = User.objects.create_user(email="out@example.com", password="pw")
    patient = _patient(user, other)
    mine = _report_for(user, patient, "medico")
    theirs = _report_for(other, patient, "medico")
    client = Client()
    client.force_login(user)

    listed = client.get(f"{API_URL}/reports?patient_id={patient.id}").json()
    by_id = {r["id"]: r for r in listed}

    assert set(by_id) == {str(mine.id), str(theirs.id)}
    # Los informes guardados ya no se editan, ni siquiera por su autor.
    assert by_id[str(mine.id)]["canEdit"] is False
    assert by_id[str(theirs.id)]["canEdit"] is False
    assert (by_id[str(mine.id)]["sequence"], by_id[str(theirs.id)]["sequence"]) == (1, 2)
    assert by_id[str(mine.id)]["patient"]["name"] == "Juan Pérez"
    # Quien no está asignado al paciente no ve sus informes.
    outsider_client = Client()
    outsider_client.force_login(outsider)
    assert outsider_client.get(f"{API_URL}/reports").json() == []
    assert outsider_client.get(f"{API_URL}/reports/{mine.id}").status_code == 404


def test_patient_summary_highlights_the_latest_information(user):
    patient = _patient(user)
    report = _report_for(user, patient, "medico")
    client = Client()
    client.force_login(user)

    summary = client.get(f"/{settings.URL_PREFIX}/api/patients/{patient.id}/summary").json()

    assert summary["reportCount"] == 1
    assert summary["byProfession"][0]["profession"] == "medico"
    groups = {h["group"] for h in summary["highlights"]}
    assert {"Diagnósticos", "Drogas en infusión"} <= groups
    assert all(h["reportId"] == str(report.id) for h in summary["highlights"])
    patients = client.get(f"/{settings.URL_PREFIX}/api/patients").json()
    assert patients[0]["reportCount"] == 1


def test_assistant_answers_with_valid_references_and_caches(monkeypatch, user):
    from apps.transcription import report_assistant

    patient = _patient(user)
    report = _report_for(user, patient, "medico")
    reply = {
        "respuesta": "Está con noradrenalina.",
        "referencias": [
            {"informe": report.id, "seccion": "drogas_infusion", "detalle": "noradrenalina 0,15"},
            {"informe": report.id, "seccion": "inventada", "detalle": "x"},
            {"informe": 9999, "seccion": "drogas_infusion", "detalle": "y"},
        ],
    }
    model = _use_model(monkeypatch, [json.dumps(reply)])

    first = report_assistant.ask(user, "¿Qué drogas usa?", patient.id)
    second = report_assistant.ask(user, "¿Qué drogas usa?", patient.id)

    assert first.answer == "Está con noradrenalina."
    assert [(r.reportId, r.section) for r in first.references] == [
        (str(report.id), "drogas_infusion")
    ]
    assert first.references[0].patientName == "Juan Pérez"
    assert second == first
    assert len(model.calls) == 1
    assert "INFORME" in model.calls[0][-1].content


def test_assistant_without_reports_does_not_call_the_model(monkeypatch, user):
    from apps.transcription import report_assistant

    model = _use_model(monkeypatch, [])

    answer = report_assistant.ask(user, "¿Algo?")

    assert answer.references == []
    assert model.calls == []


def test_completing_a_section_keeps_the_same_report(monkeypatch, user):
    patient = _patient(user)
    report = _report_for(user, patient, "medico", validated=False)
    record = report.extracted_record
    new_value = [
        {
            "descripcion": "Neumonía",
            "codigo_cie10": None,
            "estado": "confirmado",
            "evidencia": "agrega neumonía",
        }
    ]
    _use_model(monkeypatch, [json.dumps({"diagnosticos": new_value})])

    extraction.request_section_update(record, "diagnosticos", "Agrega neumonía confirmada")
    extraction.run_section_update(record.id, "diagnosticos", "Agrega neumonía confirmada", "")

    report.refresh_from_db()
    assert Report.objects.count() == 1
    # Al completarlo se vuelve a homologar y hay que validarlo de nuevo.
    assert report.status == Report.Status.REVIEW
    assert report.sequence == 1
    assert report.data["diagnosticos"][0]["descripcion"] == "Neumonía"


def test_report_is_saved_only_after_every_topic_is_validated(user):
    other = User.objects.create_user(email="med@example.com", password="pw")
    patient = _patient(user, other)
    report = _report_for(user, patient, validated=False)
    mine, theirs = Client(), Client()
    mine.force_login(user)
    theirs.force_login(other)
    topics = [t["id"] for t in mine.get(f"{API_URL}/reports/{report.id}").json()["topics"]]
    topic_url = f"{API_URL}/reports/{report.id}/topics"

    def put(client, topic, validated=True):
        return client.put(
            f"{topic_url}/{topic}", {"validated": validated}, content_type="application/json"
        )

    assert len(topics) > 1
    # Sin guardar, los demás profesionales del paciente todavía no lo ven.
    assert theirs.get(f"{API_URL}/reports").json() == []
    assert put(theirs, topics[0]).status_code == 404
    # Con temas sin validar no se puede guardar.
    assert mine.post(f"{API_URL}/reports/{report.id}/validate").status_code == 409

    for topic in topics[:-1]:
        assert put(mine, topic).status_code == 200
    assert mine.post(f"{API_URL}/reports/{report.id}/validate").status_code == 409
    # Un tema se puede desmarcar; uno que no existe se rechaza.
    assert topics[0] not in put(mine, topics[0], False).json()["validatedTopics"]
    assert put(mine, "no_existe").status_code == 409
    put(mine, topics[0])
    put(mine, topics[-1])

    saved = mine.post(f"{API_URL}/reports/{report.id}/validate")

    assert saved.status_code == 200, saved.content
    body = saved.json()
    assert (body["status"], body["canEdit"]) == ("done", False)
    assert set(body["validatedTopics"]) == set(topics)
    assert [r["id"] for r in theirs.get(f"{API_URL}/reports").json()] == [str(report.id)]
    # Guardado, ya no se edita: ni temas ni guardar de nuevo.
    assert put(mine, topics[0], False).status_code == 409
    assert mine.post(f"{API_URL}/reports/{report.id}/validate").status_code == 409


def test_topics_group_the_sections_of_the_report(user):
    from apps.transcription import report_services

    report = _report_for(user, _patient(user), validated=False)

    topics = {t.id: t.sections for t in report_services.topics_of(report)}

    assert "diagnosticos" in topics["assessment"]
    assert "drogas_infusion" in topics["treatment"]
    assert all("metadatos" not in sections for sections in topics.values())


def test_a_saved_report_cannot_be_completed(user):
    report = _report_for(user, _patient(user), validated=True)

    with pytest.raises(extraction.ExtractionError):
        extraction.request_section_update(report.extracted_record, "diagnosticos", "más datos")


def test_completing_a_section_only_unvalidates_its_topic(monkeypatch, user):
    from apps.transcription import report_services

    report = _report_for(user, _patient(user), validated=False)
    record = report.extracted_record
    all_topics = [t.id for t in report_services.topics_of(report)]
    report.validated_sections = all_topics
    report.save()
    new_value = [
        {"descripcion": "Neumonía", "codigo_cie10": None, "estado": "confirmado", "evidencia": "x"}
    ]
    _use_model(monkeypatch, [json.dumps({"diagnosticos": new_value})])

    extraction.request_section_update(record, "diagnosticos", "agrega neumonía")
    extraction.run_section_update(record.id, "diagnosticos", "agrega neumonía", "")

    report.refresh_from_db()
    assert set(report.validated_sections) == set(all_topics) - {"assessment"}
    assert [t.id for t in report_services.unvalidated_topics(report)] == ["assessment"]


def test_patient_summary_has_criticality_status_brief_and_treatment_pending(monkeypatch, user):
    patient = _patient(user)
    _report_for(user, patient, "medico")
    _use_model(monkeypatch, [json.dumps({"resumen": "Shock séptico abdominal en resolución."})])
    client = Client()
    client.force_login(user)

    summary = client.get(f"/{settings.URL_PREFIX}/api/patients/{patient.id}/summary").json()

    assert summary["criticality"]["level"] in {"critical", "high"}
    assert any("vasoactivo" in reason for reason in summary["criticality"]["reasons"])
    assert summary["status"].startswith("Día 3 de UCI")
    assert summary["brief"] == "Shock séptico abdominal en resolución."
    pending_groups = {h["group"] for h in summary["treatmentPending"]}
    assert pending_groups <= {"Pendientes", "Indicaciones", "Recomendaciones", "Metas del día"}
    assert "Pendientes" in pending_groups
    assert not any(h["group"] == "Pendientes" for h in summary["highlights"])


def test_summary_brief_falls_back_to_the_report_text(monkeypatch, user):
    patient = _patient(user)
    _report_for(user, patient, "medico")
    _use_model(monkeypatch, ["no es json"])
    client = Client()
    client.force_login(user)

    summary = client.get(f"/{settings.URL_PREFIX}/api/patients/{patient.id}/summary").json()

    assert summary["brief"] == _medico_record()["resumen_24h"]


def test_extraction_cache_does_not_depend_on_the_patient(monkeypatch, user):
    model = _use_model(monkeypatch, [json.dumps(_medico_record())])
    first = extraction.request_extraction(
        _transcription(user, profession="medico", patient="Box 7")
    )
    extraction.run_extraction(first.id)
    other = _patient(user, name="Otra Persona", identifier="9-9", bed="Box 2")
    transcription = _transcription(user, profession="medico", patient="Box 2")
    transcription.recording.patient = other
    transcription.recording.save()

    second = extraction.request_extraction(transcription)
    extraction.run_extraction(second.id)

    second.refresh_from_db()
    extraction_calls = [c for c in model.calls if "Términos a unificar" not in c[-1].content]
    assert len(extraction_calls) == 1
    assert second.data["metadatos"]["cama"] == "Box 2"
