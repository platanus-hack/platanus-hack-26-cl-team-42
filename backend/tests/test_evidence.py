"""Evidencia (exámenes): contradicciones con el informe, recuperación y anonimización."""

from __future__ import annotations

import copy
import json
from datetime import timedelta

import pytest
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client
from django.utils import timezone

from apps.clinical_templates import services as template_services
from apps.recordings.models import Patient, Recording
from apps.transcription import evidence_services as evidence
from apps.transcription import extraction_services as extraction
from apps.transcription import reconciliation_services as rec
from apps.transcription import report_assistant, report_services
from apps.transcription.models import Evidence, ExtractedRecord, Report, Transcription
from apps.users import shifts

API = f"/{settings.URL_PREFIX}/api"
User = get_user_model()


class FakeModel:
    name = "fake"

    def __init__(self, replies):
        self.replies = list(replies)
        self.calls = []

    def complete(self, messages):
        self.calls.append(messages)
        return self.replies.pop(0)


@pytest.fixture(autouse=True)
def offline(db, monkeypatch):
    template_services.sync_templates_from_files()
    monkeypatch.setattr(extraction, "_extraction_model", lambda: FakeModel([]))


@pytest.fixture()
def doctor(db):
    user = User.objects.create_user(
        email="medico@x.cl", password="pw", name="Dr. Rojas", profession="medico"
    )
    shifts.start_shift(user)
    return user


@pytest.fixture()
def nurse(db):
    user = User.objects.create_user(
        email="enf@x.cl", password="pw", name="EU Soto", profession="enfermeria"
    )
    shifts.start_shift(user)
    return user


@pytest.fixture()
def patient(doctor, nurse):
    patient = Patient.objects.create(name="Juan Pérez Soto", identifier="11.111.111-1", bed="Box 7")
    patient.assigned_to.add(doctor, nurse)
    return patient


def _lab(user, patient, hours_ago=1.0, **kwargs):
    return evidence.add_evidence(
        user,
        patient.id,
        kind=kwargs.get("kind", "lab"),
        title=kwargs.get("title", "Gases y química"),
        taken_at=timezone.now() - timedelta(hours=hours_ago),
        results=kwargs.get("results", []),
        findings=kwargs.get("findings", ""),
    )


def _draft(author, patient, profession, data, hours_ago=0.5) -> Report:
    recording = Recording.objects.create(
        professional=author,
        patient=patient,
        audio=SimpleUploadedFile("a.wav", b"x", "audio/wav"),
        mime_type="audio/wav",
        size_bytes=1,
        source=Recording.Source.UPLOAD,
        recorded_at=timezone.now() - timedelta(hours=hours_ago),
        profession=profession,
    )
    transcription = Transcription.objects.create(
        recording=recording, status="done", text="x", language="es", model_id="w"
    )
    record = ExtractedRecord.objects.create(
        transcription=transcription,
        template=template_services.get_active_template_for_profession(profession),
        status="done",
        data=copy.deepcopy(data),
    )
    return report_services.generate_report(record)


def _exam(name, value, unit, reading=None):
    return {"examen": name, "valor": value, "unidad": unit, "interpretacion": reading}


def test_results_are_flagged_against_their_reference_range(doctor, patient):
    item = _lab(
        doctor,
        patient,
        results=[
            {"name": "Lactato", "value": "4,8", "unit": ""},
            {"name": "K+", "value": "4.0", "unit": ""},
            {"name": "Hemocultivo", "value": "positivo", "unit": ""},
            {"name": "Valor propio", "value": "9", "unit": "u", "ref_min": "1", "ref_max": "5"},
        ],
    )

    by_name = {r["name"]: r for r in item.results}

    assert (by_name["Lactato"]["numeric"], by_name["Lactato"]["flag"]) == (4.8, "high")
    assert by_name["Lactato"]["unit"] == "mmol/L"  # unidad por defecto del examen
    assert by_name["K+"]["flag"] == "normal"  # alias de potasio
    assert by_name["Hemocultivo"]["flag"] == ""  # sin valor numérico: sin juicio
    assert by_name["Valor propio"]["flag"] == "high"  # el rango del laboratorio manda


def test_evidence_only_for_patients_assigned_to_the_user(doctor, patient):
    stranger = User.objects.create_user(email="z@x.cl", password="pw")

    with pytest.raises(evidence.EvidenceError, match="no está asignado"):
        _lab(stranger, patient, results=[{"name": "Lactato", "value": "2"}])
    with pytest.raises(evidence.EvidenceError, match="al menos un resultado"):
        _lab(doctor, patient)
    with pytest.raises(evidence.EvidenceError, match="futuro"):
        _lab(doctor, patient, hours_ago=-3, results=[{"name": "Lactato", "value": "2"}])


def test_a_new_report_is_checked_against_the_exams_and_contradictions_are_alerted(doctor, patient):
    _lab(
        doctor,
        patient,
        results=[
            {"name": "Lactato", "value": "4.8"},
            {"name": "Creatinina", "value": "2.4"},
            {"name": "Potasio", "value": "7.5"},
            {"name": "Glucosa", "value": "100"},
        ],
    )
    data = {
        "metadatos": {"cama": "Box 7"},
        "examenes": [
            _exam("Lactato", 2.1, "mmol/L", "mejor"),  # valor distinto
            _exam("Creatinina", 2.4, "mg/dL", "normal"),  # mismo valor, lectura equivocada
            _exam("Glucosa", 100, "mg/dL", "elevada"),  # lectura de alterado, valor normal
        ],
    }

    report = _draft(doctor, patient, "medico", data)

    alerts = {a["id"]: a for a in report.evidence_alerts}
    assert alerts["value:examenes:lactato"]["severity"] == "high"
    assert (
        "2.1" in alerts["value:examenes:lactato"]["message"]
        and "4.8" in alerts["value:examenes:lactato"]["message"]
    )
    assert "normal" in alerts["value:examenes:creatinina"]["message"]
    assert alerts["value:examenes:glucosa"]["severity"] == "medium"
    # El potasio es muy alto y el informe no lo menciona.
    assert alerts["omission:examenes:potasio"]["kind"] == "omission"
    assert all(a["topic"] == "exams" and a["acknowledged"] is False for a in alerts.values())
    assert report.status == Report.Status.REVIEW  # alerta, no bloquea


def test_evidence_conflicts_must_be_reviewed_before_saving_most_severe_first(doctor, patient):
    item = _lab(
        doctor,
        patient,
        results=[{"name": "Lactato", "value": "4.8"}, {"name": "Glucosa", "value": "100"}],
    )
    data = {
        "medicamentos": [{"nombre": "furosemida", "dosis": 20, "unidad": None}],
        "examenes": [
            _exam("Glucosa", 100, "mg/dL", "elevada"),  # discrepancia rutinaria (ámbar)
            _exam("Lactato", 2.1, "mmol/L"),  # contradice un examen alterado (rojo)
        ],
    }
    report = _draft(doctor, patient, "medico", data)

    pending = report_services.pending_review_items(report)

    assert [(i.id, i.severity) for i in pending] == [
        ("value:examenes:lactato", "high"),
        ("value:examenes:glucosa", "medium"),
        ("clarification:medicamentos:0:unidad", "medium"),
    ]
    # Lo dictado y la fuente que lo contradice, para mostrarlos al revisar.
    assert pending[0].itemIndex == 1
    assert (pending[0].evidenceId, pending[0].evidenceTitle) == (item.id, "Gases y química")
    with pytest.raises(report_services.ValidationError, match="3 puntos"):
        report_services.validate_report(report)

    for point in pending:
        report_services.review_item(report, point.id)

    # La alerta queda marcada como revisada (no se borra) y el informe se guarda.
    assert all(a["acknowledged"] for a in report.evidence_alerts)
    assert report_services.validate_report(report).status == Report.Status.DONE


def test_an_unmentioned_exam_does_not_block_a_report_without_an_exam_section(doctor, patient):
    exam = _lab(doctor, patient, results=[{"name": "Glucosa", "value": "280"}])
    report = _draft(doctor, patient, "kinesiologia", {"evaluacion_respiratoria": {}})
    medical_report = _draft(doctor, patient, "medico", {"examenes": []})

    assert report.evidence_alerts == []
    [omission] = medical_report.evidence_alerts
    assert (omission["kind"], omission["evidenceId"]) == ("omission", exam.id)

    # Los borradores existentes pueden tener la omisión guardada por la regla antigua.
    report.evidence_alerts = [omission]
    report.save(update_fields=["evidence_alerts"])

    out = report_services.to_out(report, doctor)
    assert out.reviewItems == [] and out.evidenceAlerts == []
    assert report_services.validate_report(report).status == Report.Status.DONE
    assert [item.id for item in evidence.list_evidence(doctor, patient.id)] == [exam.id]


def test_manual_exam_edit_rechecks_values_without_calling_the_model(monkeypatch, doctor, patient):
    _lab(doctor, patient, results=[{"name": "Lactato", "value": "4.8"}])
    report = _draft(doctor, patient, "medico", {"examenes": [_exam("Lactato", 2.1, "mmol/L")]})
    [point] = report_services.pending_review_items(report)
    assert point.alertKind == "value"

    def unexpected_model_call(*args, **kwargs):
        pytest.fail("Se invocó el modelo al editar un ítem")

    monkeypatch.setattr(evidence, "_model_alerts", unexpected_model_call)
    report_services.edit_item(
        report,
        "examenes",
        0,
        {**report.data["examenes"][0], "valor": 4.8},
        report.updated_at.isoformat(),
    )

    assert report_services.pending_review_items(report) == []


def test_a_report_consistent_with_the_exams_raises_no_alert(doctor, patient):
    _lab(doctor, patient, results=[{"name": "Lactato", "value": "1.8"}])

    report = _draft(
        doctor, patient, "medico", {"examenes": [_exam("Lactato", 1.8, "mmol/L", "normal")]}
    )

    assert report.evidence_alerts == []


def test_a_negative_study_the_report_does_not_mention_is_alerted(doctor, patient):
    _lab(
        doctor,
        patient,
        kind="culture",
        title="Cultivo de aspirado traqueal",
        findings="Sin desarrollo bacteriano a las 48 horas (negativo).",
    )
    data = {"control_respiratorio": [{"soporte": "VMI", "saturacion_o2": 95}]}

    report = _draft(doctor, patient, "medico", data)

    (alert,) = report.evidence_alerts
    assert alert["kind"] == "omission" and alert["section"] == "control_respiratorio"
    assert "Cultivo de aspirado traqueal" in alert["message"]


def test_a_negative_study_the_report_names_raises_no_alert(doctor, patient):
    _lab(
        doctor,
        patient,
        kind="culture",
        title="Cultivo de aspirado traqueal",
        findings="Sin desarrollo bacteriano (negativo).",
    )
    data = {
        "control_respiratorio": [{"soporte": "VMI", "saturacion_o2": 95}],
        "observaciones_no_estructuradas": "Aspirado traqueal negativo, sin neumonía.",
    }

    assert _draft(doctor, patient, "medico", data).evidence_alerts == []


def test_saying_the_culture_was_negative_counts_as_mentioning_it(doctor, patient):
    _lab(
        doctor,
        patient,
        kind="culture",
        title="Cultivo de aspirado traqueal",
        findings="Sin desarrollo bacteriano (negativo).",
    )
    data = {
        "control_respiratorio": [{"soporte": "VMI"}],
        "observaciones_no_estructuradas": "El cultivo salió negativo, se descarta neumonía.",
    }

    assert _draft(doctor, patient, "medico", data).evidence_alerts == []


def test_a_word_that_merely_contains_the_study_term_does_not_count_as_naming_it(doctor, patient):
    _lab(
        doctor,
        patient,
        kind="culture",
        title="Cultivo de aspirado traqueal",
        findings="Sin desarrollo bacteriano (negativo).",
    )
    data = {
        "dispositivos_invasivos": [{"tipo": "TET", "ubicacion": "orotraqueal"}],
        "control_respiratorio": [{"soporte": "VMI"}],
    }

    assert len(_draft(doctor, patient, "kinesiologia", data).evidence_alerts) == 1


def test_a_positive_study_is_not_treated_as_a_missing_negative(doctor, patient):
    _lab(
        doctor,
        patient,
        kind="culture",
        title="Hemocultivo",
        findings="Streptococcus pneumoniae, sensible a penicilina.",
    )

    report = _draft(doctor, patient, "medico", {"control_respiratorio": [{"soporte": "VMI"}]})

    assert report.evidence_alerts == []


def test_exams_far_from_the_report_time_are_not_compared(doctor, patient):
    _lab(doctor, patient, hours_ago=72, results=[{"name": "Lactato", "value": "6"}])

    report = _draft(doctor, patient, "medico", {"examenes": [_exam("Lactato", 2, "mmol/L")]})

    assert report.evidence_alerts == []


def test_new_evidence_rechecks_reports_awaiting_validation_and_keeps_reviewed_alerts(
    doctor, patient
):
    _lab(doctor, patient, results=[{"name": "Lactato", "value": "4.8"}])
    report = _draft(doctor, patient, "medico", {"examenes": [_exam("Lactato", 2.1, "mmol/L")]})
    report_services.acknowledge_alert(report, "value:examenes:lactato")

    _lab(
        doctor,
        patient,
        hours_ago=0.2,
        title="Química",
        results=[{"name": "Creatinina", "value": "3.1"}],
    )

    report.refresh_from_db()
    alerts = {a["id"]: a for a in report.evidence_alerts}
    assert alerts["value:examenes:lactato"]["acknowledged"] is True  # conserva lo ya revisado
    assert alerts["omission:examenes:creatinina"]["acknowledged"] is False  # lo nuevo, pendiente
    with pytest.raises(report_services.ValidationError):
        report_services.acknowledge_alert(report, "no-existe")


def test_a_new_result_for_a_reviewed_exam_requires_its_own_review(doctor, patient):
    _lab(doctor, patient, results=[{"name": "Lactato", "value": "4.8"}])
    report = _draft(doctor, patient, "medico", {"examenes": [_exam("Lactato", 2.1, "mmol/L")]})
    report_services.acknowledge_alert(report, "value:examenes:lactato")

    latest = _lab(doctor, patient, hours_ago=0.2, results=[{"name": "Lactato", "value": "6.2"}])
    report.refresh_from_db()

    [pending] = report_services.pending_review_items(report)
    assert pending.evidenceId == latest.id
    assert not pending.reviewed


def test_the_model_adds_concept_contradictions_and_only_for_real_sections(
    monkeypatch, doctor, patient
):
    _lab(
        doctor,
        patient,
        kind="culture",
        title="Hemocultivo",
        findings="Staphylococcus aureus en 2 de 2 frascos.",
    )
    reply = {
        "alertas": [
            {
                "seccion": "resumen_24h",
                "mensaje": "Dice «sin infección» y hay hemocultivo positivo",
                "severidad": "alta",
            },
            {"seccion": "no_existe", "mensaje": "inventada", "severidad": "alta"},
        ]
    }
    model = FakeModel([json.dumps(reply)])
    monkeypatch.setattr(extraction, "_extraction_model", lambda: model)

    report = _draft(doctor, patient, "medico", {"resumen_24h": "Sin signos de infección."})

    [alert] = report.evidence_alerts
    assert (alert["kind"], alert["severity"], alert["section"]) == (
        "concept",
        "high",
        "resumen_24h",
    )
    assert "hemocultivo positivo" in alert["message"]
    report.refresh_from_db()
    evidence.check_report(report)  # el segundo cálculo sale de la caché
    assert len(model.calls) == 1


def test_a_model_failure_never_blocks_the_report(doctor, patient):
    _lab(
        doctor,
        patient,
        kind="imaging",
        title="Radiografía",
        findings="Consolidación basal derecha.",
    )

    report = _draft(doctor, patient, "medico", {"resumen_24h": "Pulmones limpios."})

    assert report.status == Report.Status.REVIEW and report.evidence_alerts == []


def test_conflict_guidance_retrieves_the_exams_related_to_the_drug(doctor, nurse, patient):
    from apps.transcription.models import Conflict

    _lab(
        doctor,
        patient,
        results=[{"name": "Glicemia", "value": "280"}, {"name": "Lactato", "value": "1.0"}],
    )
    base = {
        "medicamentos": [{"nombre": "insulina cristalina", "dosis": 6, "unidad": "UI", "via": "SC"}]
    }
    other = {
        "medicamentos": [
            {"nombre": "insulina cristalina", "dosis": 10, "unidad": "UI", "via": "SC"}
        ]
    }
    for author, profession, data in ((doctor, "medico", base), (nurse, "enfermeria", other)):
        report = _draft(author, patient, profession, data)
        for point in report_services.pending_review_items(report):
            report_services.review_item(report, point.id)
        report_services.validate_report(report)

    conflict = Conflict.objects.get()
    guidance = rec.to_conflict_out(conflict, doctor).guidance

    assert len(guidance.evidence) == 1  # la glicemia; el lactato no se relaciona con la insulina
    assert guidance.evidence[0].startswith("Glicemia 280 mg/dL (alto)")


def test_the_anonymous_case_carries_the_exams_without_sensitive_data(doctor, nurse, patient):
    from apps.transcription.models import Conflict

    _lab(
        doctor,
        patient,
        title="Química de Juan Pérez Soto (RUT 11.111.111-1) muestra N° 884412",
        results=[
            {"name": "Creatinina de Juan Pérez", "value": "2.4"},
            {"name": "Lactato", "value": "4.8"},
        ],
        findings="Solicitado por Dr. Rojas, cama Box 7. Contacto juan@correo.cl",
    )
    base = {"alergias": [], "medicamentos": [{"nombre": "amoxicilina", "dosis": 1, "unidad": "g"}]}
    other = {"alergias": [{"agente": "penicilina", "reaccion": "rash"}]}
    for author, profession, data in ((doctor, "medico", base), (nurse, "enfermeria", other)):
        report = _draft(author, patient, profession, data)
        for point in report_services.pending_review_items(report):
            report_services.review_item(report, point.id)
        report_services.validate_report(report)
    conflict = Conflict.objects.get(kind="allergy")

    brief = rec.anonymized_brief(conflict)

    assert "Exámenes relevantes" in brief
    assert "Lactato 4.8 mmol/L (alto)" in brief and "hace 1 h" in brief
    for secret in (
        "Juan",
        "Pérez",
        "11.111.111-1",
        "Box 7",
        "884412",
        "juan@correo.cl",
        "Dr. Rojas",
    ):
        assert secret not in brief
    # Los textos libres del examen (título, hallazgos) se anonimizan igual.
    cleaned = evidence.anonymize_exam_text(
        "Solicitado por Dr. Rojas, muestra N° 884412, RUT 11.111.111-1, "
        "correo juan@correo.cl, +56 9 8765 4321",
        patient,
        ["Dr. Rojas"],
    )
    for secret in ("Dr. Rojas", "884412", "11.111.111-1", "juan@correo.cl", "8765 4321"):
        assert secret not in cleaned


def test_the_assistant_cites_exams_and_drops_invented_ones(monkeypatch, doctor, patient):
    item = _lab(doctor, patient, results=[{"name": "Lactato", "value": "4.8"}])
    report = _draft(doctor, patient, "medico", {"resumen_24h": "Shock séptico."})
    for point in report_services.pending_review_items(report):
        report_services.review_item(report, point.id)
    report_services.validate_report(report)
    reply = {
        "respuesta": "El lactato está en 4.8 mmol/L.",
        "referencias": [
            {"evidencia": item.id, "detalle": "Lactato 4.8"},
            {"evidencia": 9999, "detalle": "inventado"},
        ],
    }
    model = FakeModel([json.dumps(reply)])
    monkeypatch.setattr(extraction, "_extraction_model", lambda: model)

    answer = report_assistant.ask(doctor, "¿Cómo está el lactato?", patient.id)

    [reference] = answer.references
    assert (reference.evidenceId, reference.evidenceTitle) == (str(item.id), "Gases y química")
    assert reference.reportId is None and reference.patientName == "Juan Pérez Soto"
    assert f"EVIDENCIA {item.id}" in model.calls[0][-1].content


def test_api_loads_lists_evidence_and_acknowledges_alerts(doctor, nurse, patient):
    client = Client()
    client.force_login(doctor)
    url = f"{API}/patients/{patient.id}/evidence"
    payload = {
        "kind": "lab",
        "title": "Gases",
        "taken_at": (timezone.now() - timedelta(hours=1)).isoformat(),
        "results": [{"name": "Lactato", "value": "4.8"}],
    }

    created = client.post(url, payload, content_type="application/json")
    listed = client.get(url).json()

    assert created.status_code == 201, created.content
    assert listed[0]["results"][0]["flag"] == "high" and listed[0]["createdByName"] == "Dr. Rojas"
    assert (
        client.post(url, {**payload, "title": " "}, content_type="application/json").status_code
        == 400
    )
    outsider = Client()
    outsider.force_login(User.objects.create_user(email="o@x.cl", password="pw"))
    assert outsider.get(url).status_code == 404

    report = _draft(doctor, patient, "medico", {"examenes": [_exam("Lactato", 2.1, "mmol/L")]})
    ack = f"{API}/transcription/reports/{report.id}/alerts/value:examenes:lactato/ack"
    shown = client.get(f"{API}/transcription/reports/{report.id}").json()
    assert [a["acknowledged"] for a in shown["evidenceAlerts"]] == [False]
    assert client.post(ack).json()["evidenceAlerts"][0]["acknowledged"] is True
    nurse_client = Client()
    nurse_client.force_login(nurse)
    assert nurse_client.post(ack).status_code == 404  # solo su autor


def test_the_anonymous_case_includes_cultures_and_imaging_reports_anonymized(
    doctor, nurse, patient
):
    from apps.transcription.models import Conflict

    _lab(
        doctor,
        patient,
        kind="culture",
        title="Cultivo",
        findings=(
            "Streptococcus pneumoniae sensible a penicilina. Paciente Juan Pérez, Box 7, Dr. Rojas."
        ),
    )
    base = {"medicamentos": [{"nombre": "amoxicilina", "dosis": 1, "unidad": "g"}]}
    other = {"alergias": [{"agente": "penicilina", "reaccion": "rash"}]}
    for author, profession, data in ((doctor, "medico", base), (nurse, "enfermeria", other)):
        report = _draft(author, patient, profession, data)
        for point in report_services.pending_review_items(report):
            report_services.review_item(report, point.id)
        report_services.validate_report(report)

    brief = rec.anonymized_brief(Conflict.objects.get(kind="allergy"))

    assert "Cultivo: Streptococcus pneumoniae sensible a penicilina." in brief
    for secret in ("Juan", "Pérez", "Box 7", "Dr. Rojas"):
        assert secret not in brief


@pytest.mark.django_db
def test_abnormal_findings_prioritize_mortality_scales_and_labs():
    from apps.transcription.abnormal_services import abnormal_findings

    user = get_user_model().objects.create_user(email="ab@example.com", password="x")
    patient = Patient.objects.create(name="Paciente", identifier="9-9", bed="1")
    evidence = Evidence.objects.create(
        patient=patient,
        kind="lab",
        title="Lab",
        taken_at=timezone.now(),
        created_by=user,
        results=[
            {
                "name": "Lactato",
                "value": "4.8",
                "unit": "mmol/L",
                "numeric": 4.8,
                "ref_min": 0.5,
                "ref_max": 2.0,
                "flag": "high",
            },
            {
                "name": "Glucosa",
                "value": "150",
                "unit": "mg/dL",
                "numeric": 150.0,
                "ref_min": 70.0,
                "ref_max": 140.0,
                "flag": "high",
            },
            {
                "name": "Sodio",
                "value": "140",
                "unit": "mmol/L",
                "numeric": 140.0,
                "ref_min": 135.0,
                "ref_max": 145.0,
                "flag": "normal",
            },
        ],
    )
    data = {
        "escalas": [
            {"nombre": "SOFA", "puntaje": 11},
            {"nombre": "RASS", "puntaje": 0},
            {"nombre": "Glasgow", "puntaje": 15},
        ]
    }
    found = abnormal_findings(
        patient,
        data,
        provenance={"escalas::sofa": 17},
        visible_report_ids={17},
    )
    assert [(f.name, f.severity, f.mortality) for f in found] == [
        ("SOFA", "critical", True),
        ("Lactato", "critical", True),
        ("Glucosa", "moderate", False),
    ]
    assert [(f.evidenceId, f.reportId) for f in found] == [
        (None, "17"),
        (evidence.id, None),
        (evidence.id, None),
    ]
    assert abnormal_findings(patient, data, provenance={"escalas::sofa": 17})[0].reportId is None


def test_key_points_flag_let_cpr_and_allergies():
    from apps.transcription.summary_services import key_points

    data = {
        "ingreso": {"limitacion_esfuerzo_terapeutico": "LET: no intubar y no RCP"},
        "alergias": [{"agente": "penicilina", "reaccion": "anafilaxia"}],
    }
    labels = [p.label for p in key_points(data)]
    assert labels == ["LET", "No RCP", "No intubar", "Alergia: penicilina"]
    assert key_points({})[0].label == "LET no registrada"
    full = key_points(
        {"ingreso": {"limitacion_esfuerzo_terapeutico": "Sin limitación; manejo completo"}}
    )
    assert full[0].label == "Sin LET"


@pytest.mark.django_db
def test_patient_trends_flag_worsening_and_improving_labs():
    from apps.transcription.trends_services import patient_trends

    user = get_user_model().objects.create_user(email="tr@example.com", password="x")
    patient = Patient.objects.create(name="Paciente", identifier="8-8", bed="1")
    patient.assigned_to.add(user)
    now = timezone.now()

    def lab(hours, **values):
        results = [
            {
                "name": name,
                "value": str(v),
                "unit": "",
                "numeric": v,
                "ref_min": lo,
                "ref_max": hi,
                "flag": "high",
            }
            for name, (v, lo, hi) in values.items()
        ]
        Evidence.objects.create(
            patient=patient,
            kind="lab",
            title="Lab",
            created_by=user,
            results=results,
            taken_at=now - timedelta(hours=hours),
        )

    lab(20, Lactato=(6.0, 0.5, 2.0), Creatinina=(1.5, 0.6, 1.3))
    lab(2, Lactato=(3.0, 0.5, 2.0), Creatinina=(2.4, 0.6, 1.3))
    trends = {t.name: t for t in patient_trends(user, patient)}
    assert trends["Lactato"].status == "improving" and trends["Lactato"].mortality
    assert trends["Creatinina"].status == "worsening"
    assert patient_trends(user, patient)[0].name == "Creatinina"
