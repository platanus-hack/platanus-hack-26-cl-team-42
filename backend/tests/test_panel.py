"""Panel de agentes: pregunta libre o conflicto → discusión por rondas → recomendación final.

Las pruebas de base de datos necesitan la migración de ``Panel``/``PanelTurn``
(``pytest --nomigrations`` mientras no exista).
"""

from __future__ import annotations

import json

import pytest
from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import Client
from test_reconciliation import _save_report

from apps.recordings.models import Patient
from apps.transcription import panel_knowledge, panel_services
from apps.transcription import reconciliation_services as rec
from apps.transcription.models import (
    AgentProfile,
    Conflict,
    ConflictNote,
    ConsolidatedVersion,
    Panel,
    Reconciliation,
    Report,
)

API_URL = f"/{settings.URL_PREFIX}/api/transcription"
User = get_user_model()


class ScriptedModel:
    """Responde según el rol del prompt y guarda lo que recibió."""

    def __init__(self):
        self.calls: list[list] = []

    def __call__(self, messages):
        self.calls.append(messages)
        system = messages[0].content
        if "agente de síntesis" in system:
            return {
                "resumen": "Hay consenso en tratar la alergia como real.",
                "recomendacion": "Suspender la penicilina y usar una alternativa.",
                "acuerdos": ["La alergia debe prevalecer"],
                "desacuerdos": [],
                "siguientes_pasos": ["Confirmar con la familia"],
                "confianza": "alta",
            }
        return {"postura": "Tratar como alergia real", "opinion": "Por seguridad, suspender."}


@pytest.fixture()
def model(monkeypatch):
    scripted = ScriptedModel()
    monkeypatch.setattr(panel_services, "_complete", scripted)
    return scripted


@pytest.fixture(autouse=True)
def run_tasks_inline(monkeypatch):
    # En las pruebas no hay worker: el encargo corre al confirmarse la transacción.
    monkeypatch.setattr(
        panel_services, "_enqueue", lambda panel_id: panel_services.run_panel(panel_id)
    )


@pytest.fixture()
def doctor(db):
    return User.objects.create_user(
        email="medico@example.com", password="pw", name="Dr. Rojas", profession="medico"
    )


@pytest.fixture()
def nurse(db):
    return User.objects.create_user(
        email="enfermera@example.com", password="pw", name="EU Soto", profession="enfermeria"
    )


@pytest.fixture()
def outsider(db):
    return User.objects.create_user(
        email="otro@example.com", password="pw", name="Otro", profession="medico"
    )


@pytest.fixture()
def patient(doctor, nurse):
    patient = Patient.objects.create(name="Juan Pérez Soto", identifier="11.111.111-1", bed="Box 7")
    patient.assigned_to.add(doctor, nurse)
    return patient


def _client(user) -> Client:
    client = Client()
    client.force_login(user)
    return client


def _post(user, path: str, body: dict):
    return _client(user).post(
        f"{API_URL}{path}", data=json.dumps(body), content_type="application/json"
    )


@pytest.mark.django_db(transaction=True)
def test_free_question_runs_rounds_and_a_single_synthesis(doctor, nurse, patient, model):
    response = _post(doctor, "/panels", {"patient_id": patient.id, "question": "¿Dosis de vanco?"})

    assert response.status_code == 200
    panel = Panel.objects.get(pk=response.json()["id"])
    assert panel.status == Panel.Status.DONE
    # 2 agentes x 2 rondas, y una sola síntesis que cierra la discusión.
    assert panel.turns.count() == 4
    assert sorted(panel.turns.values_list("round", flat=True)) == [1, 1, 2, 2]
    assert sum("agente de síntesis" in c[0].content for c in model.calls) == 1
    assert panel.recommendation["recomendacion"].startswith("Suspender")
    assert panel.recommendation["confianza"] == "alta"
    assert panel.recommendation["aviso"]


@pytest.mark.django_db(transaction=True)
def test_second_round_sees_the_other_opinions(doctor, nurse, patient, model):
    _post(doctor, "/panels", {"patient_id": patient.id, "question": "¿Cambiar el antibiótico?"})

    reply_prompts = [c[1].content for c in model.calls if "réplica" in c[0].content]
    assert len(reply_prompts) == 2
    assert all("Opiniones de la ronda anterior" in prompt for prompt in reply_prompts)


@pytest.mark.django_db(transaction=True)
def test_model_never_receives_the_patient_identity(doctor, nurse, patient, model):
    _post(doctor, "/panels", {"patient_id": patient.id, "question": "¿Qué hacemos?"})

    sent = "\n".join(m.content for call in model.calls for m in call)
    assert "11.111.111-1" not in sent
    assert "Juan" not in sent


@pytest.mark.django_db
def test_free_question_requires_an_assigned_patient(outsider, patient, model):
    response = _post(outsider, "/panels", {"patient_id": patient.id, "question": "¿Hola?"})

    assert response.status_code == 404


@pytest.mark.django_db
def test_empty_question_is_rejected(doctor, patient, model):
    response = _post(doctor, "/panels", {"patient_id": patient.id, "question": "  "})

    assert response.status_code == 422


@pytest.mark.django_db
def test_needs_at_least_two_professionals_in_the_areas(doctor, model):
    nutritionist = User.objects.create_user(
        email="nutri@example.com", password="pw", name="Nut", profession="nutricionista"
    )
    alone = Patient.objects.create(name="Solo Uno")
    alone.assigned_to.add(nutritionist)

    response = _post(nutritionist, "/panels", {"patient_id": alone.id, "question": "¿Y ahora?"})

    assert response.status_code == 422


@pytest.mark.django_db
def test_every_professional_of_the_area_opines_even_if_not_assigned(
    doctor, nurse, outsider, patient, model
):
    # «Otro» es médico como Tomás pero no tiene asignado al paciente: igual opina.
    panel = panel_services.open_panel(doctor, patient, "¿Dosis?")

    names = sorted(panel.participants.values_list("email", flat=True))
    assert names == ["enfermera@example.com", "medico@example.com", "otro@example.com"]


@pytest.mark.django_db
def test_the_areas_can_be_chosen_and_add_professionals_of_other_areas(
    doctor, nurse, patient, model
):
    nutritionist = User.objects.create_user(
        email="nutri@example.com", password="pw", name="Nut", profession="nutricionista"
    )

    panel = panel_services.open_panel(
        doctor, patient, "¿Aporte proteico?", areas=["medico", "nutricionista"]
    )

    assert set(panel.participants.values_list("email", flat=True)) == {
        doctor.email,
        nutritionist.email,
    }


@pytest.mark.django_db
def test_a_conflict_panel_includes_every_professional_of_both_areas(
    doctor, nurse, outsider, patient, conflict, model
):
    panel = panel_services.open_panel(doctor, patient, "", conflict=conflict)

    # Los dos autores (médico y enfermería) y el resto de los médicos, aunque no sean del caso.
    assert set(panel.participants.values_list("email", flat=True)) == {
        doctor.email,
        nurse.email,
        outsider.email,
    }


@pytest.mark.django_db(transaction=True)
def test_a_model_failure_leaves_a_failed_panel_with_the_error(doctor, nurse, patient, monkeypatch):
    def broken(messages):
        raise ValueError("sin créditos")

    monkeypatch.setattr(panel_services, "_complete", broken)

    response = _post(doctor, "/panels", {"patient_id": patient.id, "question": "¿Dosis?"})

    panel = Panel.objects.get(pk=response.json()["id"])
    assert panel.status == Panel.Status.FAILED
    assert "sin créditos" in panel.error
    assert panel.recommendation is None


@pytest.mark.django_db
def test_panels_are_only_visible_to_the_patients_team(doctor, nurse, outsider, patient, model):
    panel = panel_services.open_panel(doctor, patient, "¿Dosis?")

    assert _client(nurse).get(f"{API_URL}/panels/{panel.id}").status_code == 200
    assert _client(outsider).get(f"{API_URL}/panels/{panel.id}").status_code == 404
    assert _client(outsider).get(f"{API_URL}/panels").json() == []


@pytest.fixture()
def conflict(doctor, nurse, patient):
    version = ConsolidatedVersion.objects.create(
        patient=patient, version=1, data={"alergias": []}, reason="official"
    )
    report = Report.objects.create(
        extracted_record=_record(doctor), author=nurse, profession="enfermeria", patient=patient
    )
    reconciliation = Reconciliation.objects.create(
        patient=patient, report=report, base_version=version
    )
    side = lambda user, value: {  # noqa: E731
        "reportId": report.id,
        "authorId": user.id,
        "authorName": user.name,
        "profession": user.profession,
        "value": value,
        "evidence": "",
    }
    conflict = Conflict.objects.create(
        reconciliation=reconciliation,
        key="allergy:penicilina",
        kind="allergy",
        section="alergias",
        label="Alergia a penicilina",
        side_a=side(nurse, "alergia a penicilina"),
        side_b=side(doctor, "sin alergias"),
    )
    conflict.guidance = rec.rule_guidance(conflict)
    conflict.save(update_fields=["guidance"])
    return conflict


def _record(author):
    from django.core.files.uploadedfile import SimpleUploadedFile

    from apps.clinical_templates import services as template_services
    from apps.recordings.models import Recording
    from apps.transcription.models import ExtractedRecord, Transcription

    template_services.sync_templates_from_files()
    recording = Recording.objects.create(
        professional=author,
        audio=SimpleUploadedFile("a.wav", b"x", "audio/wav"),
        mime_type="audio/wav",
        size_bytes=1,
        source=Recording.Source.UPLOAD,
        recorded_at="2026-11-19T10:00:00Z",
        profession=author.profession,
    )
    transcription = Transcription.objects.create(
        recording=recording, status=Transcription.Status.DONE, text="x", language="es", model_id="w"
    )
    return ExtractedRecord.objects.create(
        transcription=transcription,
        template=template_services.get_active_template_for_profession(author.profession),
        status=ExtractedRecord.Status.DONE,
        data={},
    )


@pytest.mark.django_db(transaction=True)
def test_a_panel_can_start_from_a_conflict_without_writing_in_its_notes(
    doctor, nurse, patient, conflict, model
):
    response = _post(doctor, "/panels", {"conflict_id": conflict.id})

    assert response.status_code == 200
    body = response.json()
    assert body["conflictId"] == str(conflict.id)
    assert "Alergia a penicilina" in body["question"]
    panel = Panel.objects.get(pk=body["id"])
    assert panel.status == Panel.Status.DONE
    # Las notas del conflicto son solo de los profesionales: los agentes no escriben ahí.
    assert not ConflictNote.objects.filter(conflict=conflict).exists()
    assert panel.recommendation["recomendacion"].startswith("Suspender la penicilina")
    # El contexto del conflicto llegó a los agentes.
    assert any("Discrepancia" in c[1].content for c in model.calls)


@pytest.mark.django_db
def test_knowledge_is_built_from_the_professionals_own_reports(doctor, patient):
    _save_report(
        doctor,
        patient,
        "medico",
        {
            "metadatos": {"tipo_profesional": "medico"},
            "medicamentos": [{"nombre": "vancomicina", "dosis": 1, "unidad": "g", "via": "EV"}],
        },
    )

    knowledge = panel_knowledge.knowledge_for(doctor, "¿Ajustar la vancomicina?")

    assert "1 informes" in knowledge.profile
    assert "Vancomicina" in knowledge.profile or "vancomicina" in knowledge.profile
    assert knowledge.cases and "vancomicina" in knowledge.cases[0].lower()
    assert "Juan" not in knowledge.cases[0]
    assert panel_knowledge.knowledge_for(doctor, "tema sin relación alguna xyz").cases == []


@pytest.mark.django_db(transaction=True)
def test_a_clinic_member_without_an_account_also_opines(doctor, nurse, patient, model):
    profile = AgentProfile.objects.create(
        name="Dra. Rojas", profession="medico", experience="Infectóloga: desescala a las 48 h."
    )
    AgentProfile.objects.create(name="Inactiva", profession="medico", is_active=False)
    AgentProfile.objects.create(name="Otra área", profession="nutricionista")

    response = _post(doctor, "/panels", {"patient_id": patient.id, "question": "¿Antibiótico?"})

    panel = Panel.objects.get(pk=response.json()["id"])
    assert list(panel.profiles.all()) == [profile]
    # 3 agentes (médico, enfermera y el perfil sin cuenta) x 2 rondas.
    assert panel.turns.count() == 6
    turn = panel.turns.filter(profile=profile).first()
    assert turn.represents is None and turn.profession == "medico"
    # Su experiencia llegó a su agente, y aparece en lo que ve el equipo.
    assert any("desescala a las 48 h" in c[0].content for c in model.calls)
    assert any("Dra. Rojas" in label for label in response.json()["participants"])
    assert "Dra. Rojas · Médico UCI" in {t["author"] for t in response.json()["turns"]}


@pytest.mark.django_db
def test_profiles_count_toward_the_two_participants_minimum(doctor, patient, model):
    alone = Patient.objects.create(name="Solo Uno")
    alone.assigned_to.add(doctor)
    # Sin el perfil solo hay médicos que ya cuentan (doctor); con un perfil sin cuenta alcanza.
    User.objects.exclude(pk=doctor.pk).delete()
    AgentProfile.objects.create(name="Dra. Rojas", profession="medico")

    panel = panel_services.open_panel(doctor, alone, "¿Dosis?")

    assert panel.participants.count() == 1 and panel.profiles.count() == 1


@pytest.mark.django_db
def test_a_profile_only_joins_the_areas_of_the_consultation(doctor, nurse, patient, model):
    nutrition = AgentProfile.objects.create(name="Nut. Pinto", profession="nutricionista")

    free = panel_services.open_panel(doctor, patient, "¿Aporte?")
    chosen = panel_services.open_panel(
        doctor, patient, "¿Aporte?", areas=["medico", "nutricionista"]
    )

    assert free.profiles.count() == 0
    assert list(chosen.profiles.all()) == [nutrition]


@pytest.mark.django_db
def test_the_agent_profiles_loader_is_idempotent_and_has_two_per_area():
    from collections import Counter
    from io import StringIO

    from django.core.management import call_command

    from apps.clinical_templates.models import ClinicalTemplate

    call_command("load_agent_profiles", stdout=StringIO())
    call_command("load_agent_profiles", stdout=StringIO())

    per_area = Counter(AgentProfile.objects.values_list("profession", flat=True))
    assert set(per_area) == set(ClinicalTemplate.Profession.values)
    assert all(count >= 2 for count in per_area.values())
    assert AgentProfile.objects.count() == sum(per_area.values()) == 12
    assert not AgentProfile.objects.filter(experience="").exists()
