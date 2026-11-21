"""ICU clinical templates: schema rules, examples, DB sync/versioning and API."""

from __future__ import annotations

import copy
import json

import pytest
from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import Client
from jsonschema import Draft202012Validator

from apps.clinical_templates import services
from apps.clinical_templates.models import ClinicalTemplate

API_URL = f"/{settings.URL_PREFIX}/api/clinical-templates"
EXPECTED_SLUGS = [
    "enfermeria_uci",
    "especialista_interconsulta",
    "kinesiologia_uci",
    "medico_uci",
    "nutricionista_uci",
    "tens_uci",
]
User = get_user_model()


@pytest.fixture()
def auth_client(db):
    """A Django test client authenticated as a superuser."""
    user = User.objects.create_superuser(email="test@example.com", password="pw")
    c = Client()
    c.force_login(user)
    return c


@pytest.fixture()
def synced(db):
    services.sync_templates_from_files()


def test_template_files_are_discovered():
    assert services.list_template_slugs() == EXPECTED_SLUGS


@pytest.mark.parametrize("slug", EXPECTED_SLUGS)
def test_built_schema_is_valid_json_schema(slug):
    built = services.build_template_schema(slug)
    Draft202012Validator.check_schema(built.output_schema)
    assert built.llm_instructions


@pytest.mark.parametrize("slug", EXPECTED_SLUGS)
def test_every_object_requires_all_properties_and_forbids_extras(slug):
    """Structured-output engines need every key required and no extras."""
    schema = services.build_template_schema(slug).output_schema
    for path, node in _object_nodes(schema):
        assert node.get("additionalProperties") is False, path
        assert sorted(node.get("required", [])) == sorted(node["properties"]), path


@pytest.mark.parametrize("slug", EXPECTED_SLUGS)
def test_every_template_carries_the_common_envelope(slug):
    common = json.loads(services.common_path.read_text(encoding="utf-8"))
    props = services.build_template_schema(slug).output_schema["properties"]
    for key, definition in common["x-sobre-comun"].items():
        if key == "metadatos":
            continue
        assert props[key] == definition, key


@pytest.mark.parametrize("slug", EXPECTED_SLUGS)
def test_metadatos_pins_the_profession(slug):
    built = services.build_template_schema(slug)
    metadatos = built.output_schema["properties"]["metadatos"]["properties"]
    assert metadatos["tipo_profesional"]["const"] == built.profession


@pytest.mark.parametrize("slug", EXPECTED_SLUGS)
def test_example_record_is_valid(slug):
    schema = services.build_template_schema(slug).output_schema
    example = _example(slug)
    errors = list(Draft202012Validator(schema).iter_errors(example))
    assert errors == [], [e.message for e in errors]


def test_examples_describe_the_same_icu_day():
    """The examples form one cross-professional scenario for reconciliation demos."""
    beds = {_example(slug)["metadatos"]["cama"] for slug in EXPECTED_SLUGS}
    days = {_example(slug)["metadatos"]["dia_estada_uci"] for slug in EXPECTED_SLUGS}
    assert beds == {"Box 7"}
    assert days == {3}


def test_especialista_requires_especialidad():
    schema = services.build_template_schema("especialista_interconsulta").output_schema
    example = _example("especialista_interconsulta")
    example["metadatos"]["especialidad"] = None
    assert list(Draft202012Validator(schema).iter_errors(example))


@pytest.mark.django_db
def test_sync_is_idempotent():
    first = services.sync_templates_from_files()
    second = services.sync_templates_from_files()

    assert all(r.created and r.version == 1 for r in first)
    assert all(not r.created and r.version == 1 for r in second)
    assert ClinicalTemplate.objects.count() == len(EXPECTED_SLUGS)


@pytest.mark.django_db
def test_sync_creates_new_version_when_content_changes(monkeypatch):
    services.sync_templates_from_files()
    original_build = services.build_template_schema

    def changed_build(slug):
        built = original_build(slug)
        if slug == "tens_uci":
            built.llm_instructions += "\nNueva regla."
            built.content_hash = "changed"
        return built

    monkeypatch.setattr(services, "build_template_schema", changed_build)
    results = {r.slug: r for r in services.sync_templates_from_files()}

    assert results["tens_uci"].created and results["tens_uci"].version == 2
    assert not results["medico_uci"].created
    versions = ClinicalTemplate.objects.filter(slug="tens_uci").order_by("version")
    assert [(t.version, t.is_active) for t in versions] == [(1, False), (2, True)]


@pytest.mark.django_db
def test_validate_record_reports_extra_keys_and_wrong_types(synced):
    template = services.get_active_template("medico_uci")
    record = _example("medico_uci")
    record["inventado"] = "x"
    record["control_hemodinamico"][0]["pam"] = "setenta"

    issues = services.validate_record(template, record)

    paths = {issue.path for issue in issues}
    assert "$" in paths
    assert "$.control_hemodinamico[0].pam" in paths


def test_api_list_templates(auth_client, synced):
    response = auth_client.get(f"{API_URL}/")

    assert response.status_code == 200
    assert sorted(t["slug"] for t in response.json()) == EXPECTED_SLUGS


def test_api_get_template_detail(auth_client, synced):
    response = auth_client.get(f"{API_URL}/kinesiologia_uci")

    assert response.status_code == 200
    body = response.json()
    assert body["version"] == 1
    assert body["output_schema"]["title"] == "Registro de kinesiología UCI"
    assert "UCI" in body["llm_instructions"]


def test_api_get_unknown_template_returns_404(auth_client, synced):
    assert auth_client.get(f"{API_URL}/no_existe").status_code == 404


def test_api_validate_accepts_valid_record(auth_client, synced):
    response = auth_client.post(
        f"{API_URL}/enfermeria_uci/validate",
        data=_example("enfermeria_uci"),
        content_type="application/json",
    )

    assert response.status_code == 200, response.content
    assert response.json() == {
        "valid": True,
        "template_slug": "enfermeria_uci",
        "template_version": 1,
        "errors": [],
    }


def test_api_validate_rejects_invalid_record(auth_client, synced):
    record = _example("enfermeria_uci")
    del record["metadatos"]

    response = auth_client.post(
        f"{API_URL}/enfermeria_uci/validate", data=record, content_type="application/json"
    )

    assert response.status_code == 200
    body = response.json()
    assert body["valid"] is False
    assert any("metadatos" in e["message"] for e in body["errors"])


def _object_nodes(node, path="$"):
    if isinstance(node, dict):
        if "properties" in node:
            yield path, node
        for key, value in node.items():
            yield from _object_nodes(value, f"{path}.{key}")
    elif isinstance(node, list):
        for i, item in enumerate(node):
            yield from _object_nodes(item, f"{path}[{i}]")


def _example(slug):
    path = services.examples_dir / f"{slug}.json"
    return copy.deepcopy(json.loads(path.read_text(encoding="utf-8")))


@pytest.mark.django_db
def test_templates_load_themselves_on_first_use():
    assert not ClinicalTemplate.objects.exists()

    template = services.get_active_template_for_profession("kinesiologia")

    assert template.slug == "kinesiologia_uci"
