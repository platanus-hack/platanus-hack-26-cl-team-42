"""Cambios entre informes de la misma profesión y su impacto en el registro oficial."""

from __future__ import annotations

import pytest
from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import Client
from test_reconciliation import FakeModel, _base_data, _save_report

from apps.clinical_templates import services as template_services
from apps.transcription import diff_services
from apps.transcription import extraction_services as extraction
from apps.transcription import reconciliation_services as rec
from apps.transcription.models import ConsolidatedVersion
from apps.users import shifts

User = get_user_model()


@pytest.fixture(autouse=True)
def templates(db):
    template_services.sync_templates_from_files()


@pytest.fixture(autouse=True)
def offline_model(monkeypatch):
    monkeypatch.setattr(extraction, "_extraction_model", lambda: FakeModel([]))


@pytest.fixture()
def doctor(db):
    return User.objects.create_user(
        email="medico@example.com", password="pw", name="Dr. Rojas", profession="medico"
    )


@pytest.fixture()
def second_doctor(db):
    return User.objects.create_user(
        email="medico2@example.com", password="pw", name="Dra. Vidal", profession="medico"
    )


@pytest.fixture()
def nurse(db):
    return User.objects.create_user(
        email="enfermera@example.com", password="pw", name="EU Soto", profession="enfermeria"
    )


@pytest.fixture(autouse=True)
def on_duty(doctor, second_doctor, nurse):
    for professional in (doctor, second_doctor, nurse):
        shifts.start_shift(professional)


@pytest.fixture()
def patient(doctor, second_doctor, nurse):
    from apps.recordings.models import Patient

    patient = Patient.objects.create(name="Juan Pérez Soto", identifier="11.111.111-1", bed="Box 7")
    patient.assigned_to.add(doctor, second_doctor, nurse)
    return patient


def _by_key(diff) -> dict[str, diff_services.ReportChange]:
    return {change.key: change for change in diff.changes}


def test_diff_data_is_semantic_and_reports_absence_as_not_mentioned():
    before = {
        "drogas_infusion": [{"farmaco": "Noradrenalina", "dosis": 0.15, "unidad": "mcg/kg/min"}],
        "dispositivos_invasivos": [{"tipo": "CVC", "ubicacion": "yugular derecha"}],
        "balance_hidrico": {"balance_ml": 450, "diuresis_ml": 1200},
        "resumen_24h": "Estable.",
    }
    after = {
        "drogas_infusion": [
            {"farmaco": "noradrenalina", "dosis": 0.3, "unidad": "mcg/kg/min", "via": "CVC"}
        ],
        "antimicrobianos": [{"farmaco": "Meropenem", "dosis": 1, "unidad": "g"}],
        "balance_hidrico": {"balance_ml": 450},
        "resumen_24h": "Mayor requerimiento de vasoactivos.",
    }

    changes = {c.key: c for c in diff_services.diff_data(before, after)}

    dose = changes["drogas_infusion:noradrenalina:dosis"]
    assert (dose.kind, dose.before, dose.after) == ("changed", "0.15 mcg/kg/min", "0.3 mcg/kg/min")
    assert changes["antimicrobianos:meropenem"].kind == "added"
    # Un dato que antes no estaba es nuevo, no un cambio.
    via = changes["drogas_infusion:noradrenalina:via"]
    assert (via.kind, via.before, via.after) == ("added", "", "CVC")
    assert "antimicrobianos:meropenem:dosis" not in changes  # va dentro de «agregado»
    assert changes["dispositivos_invasivos:cvc"].kind == "removed"
    assert changes["resumen_24h"].kind == "updated"
    # Un campo que el informe nuevo no menciona no es un cambio.
    assert "balance_hidrico::diuresis_ml" not in changes
    assert "balance_hidrico::balance_ml" not in changes


def test_report_diff_compares_with_the_previous_report_of_the_same_profession(
    doctor, second_doctor, nurse, patient
):
    first = _save_report(doctor, patient, "medico", _base_data())
    _save_report(nurse, patient, "enfermeria", {"balance_hidrico": {"balance_ml": 100}})
    data = _base_data()
    data["dispositivos_invasivos"] = []
    data["pendientes"].append({"descripcion": "Ecocardiograma", "plazo": "mañana"})
    data["balance_hidrico"] = {"diuresis_ml": 800}
    second = _save_report(second_doctor, patient, "medico", data)

    diff = diff_services.report_diff(second_doctor, second)

    assert diff.previous is not None and diff.previous.id == str(first.id)
    assert diff.preview is False
    changes = _by_key(diff)
    # El CVC no se mencionó: sigue vigente en el registro oficial.
    cvc = changes["dispositivos_invasivos:cateter venoso central"]
    assert (cvc.kind, cvc.impact) == ("removed", "still_in_record")
    echo = changes["pendientes:ecocardiograma"]
    assert (echo.kind, echo.impact) == ("added", "in_record")
    # El balance de enfermería no es de esta profesión: para medicina es dato nuevo.
    assert changes["balance_hidrico::diuresis_ml"].impact == "in_record"


def test_a_changed_dose_is_reported_as_a_conflict_while_reconciling(doctor, second_doctor, patient):
    _save_report(doctor, patient, "medico", _base_data())
    data = _base_data()
    data["drogas_infusion"][0]["dosis"] = 0.3
    report = _save_report(second_doctor, patient, "medico", data)

    dose = _by_key(diff_services.report_diff(second_doctor, report))[
        "drogas_infusion:noradrenalina:dosis"
    ]

    assert (dose.kind, dose.before, dose.after) == (
        "changed",
        "0.15 mcg/kg/min",
        "0.3 mcg/kg/min",
    )
    assert dose.impact == "conflict"

    # Resuelto a favor del valor anterior: el registro oficial mantiene 0,15.
    conflict = report.reconciliations.get().conflicts.get()
    rec.accept_other(conflict, second_doctor)
    report.refresh_from_db()
    dose = _by_key(diff_services.report_diff(second_doctor, report))[
        "drogas_infusion:noradrenalina:dosis"
    ]
    assert (dose.impact, dose.officialValue) == ("official_differs", "0.15 mcg/kg/min")


def test_a_draft_previews_its_impact(doctor, second_doctor, patient):
    from apps.transcription import report_services

    _save_report(doctor, patient, "medico", _base_data())
    data = _base_data()
    data["drogas_infusion"][0]["dosis"] = 0.3
    data["antimicrobianos"] = [{"farmaco": "Vancomicina", "dosis": 1, "unidad": "g"}]
    draft = _save_report(second_doctor, patient, "medico", data)
    # Lo dejamos como borrador para simular que aún no se guarda.
    draft.status = draft.Status.REVIEW
    draft.save()
    ConsolidatedVersion.objects.filter(patient=patient).exclude(version=1).delete()
    draft.reconciliations.all().delete()

    diff = diff_services.report_diff(second_doctor, draft)

    assert diff.preview is True
    changes = _by_key(diff)
    assert changes["drogas_infusion:noradrenalina:dosis"].impact == "conflict"
    assert changes["antimicrobianos:vancomicina"].impact == "in_record"
    assert report_services.get_report(second_doctor, draft.id) is not None


def test_the_first_report_of_a_profession_has_no_previous(doctor, patient):
    report = _save_report(doctor, patient, "medico", _base_data())

    diff = diff_services.report_diff(doctor, report)

    assert diff.previous is None
    assert all(change.kind == "added" for change in diff.changes)
    assert all(change.impact == "in_record" for change in diff.changes)


def test_api_exposes_report_diff_and_version_changes(doctor, nurse, patient):
    _save_report(doctor, patient, "medico", _base_data())
    nurse_report = _save_report(
        nurse,
        patient,
        "enfermeria",
        {"balance_hidrico": {"balance_ml": 450}, "pendientes": [{"descripcion": "Curación"}]},
    )
    client = Client()
    client.force_login(nurse)

    response = client.get(
        f"/{settings.URL_PREFIX}/api/transcription/reports/{nurse_report.id}/diff"
    )
    assert response.status_code == 200
    assert response.json()["previous"] is None

    versions = client.get(f"/{settings.URL_PREFIX}/api/patients/{patient.id}/versions").json()
    latest = next(v for v in versions if v["version"] == 2)
    keys = {c["key"]: c["kind"] for c in latest["changes"]}
    assert keys["pendientes:curacion"] == "added"
    assert keys["balance_hidrico::balance_ml"] == "added"  # no había balance
    assert next(v for v in versions if v["version"] == 1)["changes"] == []
