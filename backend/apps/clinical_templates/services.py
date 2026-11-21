"""Business logic for ICU clinical templates.

Template files live in ``data/``:

- ``comun.json`` holds the shared ``$defs`` (vital support, clinical items,
  per-system assessment), the common root envelope every template carries
  (``x-sobre-comun``) and the base LLM instructions (``x-instrucciones-base``).
- ``<slug>.json`` holds one profession's specific root properties plus an
  ``x-plantilla`` metadata block.

``build_template_schema`` merges both into a single self-contained JSON Schema
(Draft 2020-12) that can be handed to Qwen as ``response_format`` and used to
validate its output. ``sync_templates_from_files`` stores those schemas in the
database, creating a new version whenever a template's content changes.
"""

from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
from typing import Any

from django.db import transaction
from jsonschema import Draft202012Validator
from pydantic import BaseModel

from .models import ClinicalTemplate

data_dir = Path(__file__).parent / "data"
examples_dir = data_dir / "ejemplos"
common_path = data_dir / "comun.json"

JSON_SCHEMA_DIALECT = "https://json-schema.org/draft/2020-12/schema"


class BuiltTemplate(BaseModel):
    """A template ready to be stored: merged schema plus its metadata."""

    slug: str
    name: str
    description: str
    profession: str
    output_schema: dict[str, Any]
    llm_instructions: str
    content_hash: str


class SyncResult(BaseModel):
    """What ``sync_templates_from_files`` did for one template slug."""

    slug: str
    version: int
    created: bool


class ValidationIssue(BaseModel):
    """A single JSON Schema violation in an extracted record."""

    path: str
    message: str


def sync_templates_from_files() -> list[SyncResult]:
    """Upsert every template file into the database, versioning on change.

    Idempotent: when the stored active version already has the same content
    hash nothing is written. Otherwise a new version is created, activated,
    and every previous version of that slug is deactivated.
    """
    return [_sync_one(build_template_schema(slug)) for slug in list_template_slugs()]


def list_template_slugs() -> list[str]:
    """Slugs of the template files in ``data/`` (``comun.json`` excluded)."""
    return sorted(p.stem for p in data_dir.glob("*.json") if p != common_path)


def build_template_schema(slug: str) -> BuiltTemplate:
    """Merge ``comun.json`` with ``<slug>.json`` into a self-contained schema."""
    common = _read_json(common_path)
    template = _read_json(data_dir / f"{slug}.json")
    meta = template["x-plantilla"]

    properties = {**copy.deepcopy(common["x-sobre-comun"]), **template["properties"]}
    properties["metadatos"] = _metadatos_property(common["$defs"]["Metadatos"], meta)

    schema: dict[str, Any] = {
        "$schema": JSON_SCHEMA_DIALECT,
        "title": template["title"],
        "description": template["description"],
        "type": "object",
        "properties": properties,
        "required": list(properties),
        "additionalProperties": False,
    }
    schema["$defs"] = _used_defs(schema, common["$defs"])

    base_instructions = common["x-instrucciones-base"].strip()
    instructions = f"{base_instructions}\n\n{meta['instrucciones_llm'].strip()}"
    return BuiltTemplate(
        slug=meta["slug"],
        name=meta["nombre"],
        description=meta["descripcion"],
        profession=meta["profesion"],
        output_schema=schema,
        llm_instructions=instructions,
        content_hash=_content_hash(schema, instructions),
    )


def get_active_template(slug: str) -> ClinicalTemplate:
    """The active version of a template. Raises ``DoesNotExist`` if missing."""
    return ClinicalTemplate.objects.get(slug=slug, is_active=True)


def get_active_template_for_profession(profession: str) -> ClinicalTemplate:
    """The active template of a profession. Raises ``DoesNotExist`` if missing."""
    return ClinicalTemplate.objects.get(profession=profession, is_active=True)


def validate_record(template: ClinicalTemplate, payload: Any) -> list[ValidationIssue]:
    """Validate an extracted record against a template; empty list means valid."""
    validator = Draft202012Validator(template.output_schema)
    errors = sorted(validator.iter_errors(payload), key=lambda e: list(e.absolute_path))
    return [
        ValidationIssue(path=_json_path(error.absolute_path), message=error.message)
        for error in errors
    ]


def _sync_one(built: BuiltTemplate) -> SyncResult:
    with transaction.atomic():
        versions = ClinicalTemplate.objects.select_for_update().filter(slug=built.slug)
        active = versions.filter(is_active=True).first()
        if active and active.content_hash == built.content_hash:
            return SyncResult(slug=built.slug, version=active.version, created=False)

        latest = versions.order_by("-version").first()
        versions.update(is_active=False)
        template = ClinicalTemplate.objects.create(
            **built.model_dump(),
            version=(latest.version + 1) if latest else 1,
            is_active=True,
        )
    return SyncResult(slug=template.slug, version=template.version, created=True)


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _metadatos_property(metadatos_def: dict[str, Any], meta: dict[str, Any]) -> dict[str, Any]:
    """Inline ``Metadatos`` specialised for one template.

    Pins ``tipo_profesional`` to the template's profession, restricts
    ``tipo_registro`` to the record types that profession produces, and makes
    ``especialidad`` mandatory when the template requires it.
    """
    metadatos = copy.deepcopy(metadatos_def)
    props = metadatos["properties"]
    props["tipo_profesional"] = {
        "type": "string",
        "const": meta["profesion"],
        "description": props["tipo_profesional"]["description"],
    }
    props["tipo_registro"]["enum"] = [*meta["tipos_registro"], None]
    if meta.get("especialidad_obligatoria"):
        props["especialidad"]["type"] = "string"
    return metadatos


def _used_defs(schema: dict[str, Any], defs: dict[str, Any]) -> dict[str, Any]:
    """Only the ``$defs`` reachable from ``schema``, to keep prompts small."""
    used: dict[str, Any] = {}
    pending = list(_refs_in(schema))
    while pending:
        name = pending.pop()
        if name in used:
            continue
        used[name] = defs[name]
        pending.extend(_refs_in(defs[name]))
    return dict(sorted(used.items()))


def _refs_in(node: Any) -> list[str]:
    if isinstance(node, dict):
        found = []
        ref = node.get("$ref")
        if isinstance(ref, str) and ref.startswith("#/$defs/"):
            found.append(ref.removeprefix("#/$defs/"))
        for value in node.values():
            found.extend(_refs_in(value))
        return found
    if isinstance(node, list):
        return [ref for item in node for ref in _refs_in(item)]
    return []


def _content_hash(schema: dict[str, Any], instructions: str) -> str:
    payload = json.dumps([schema, instructions], sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _json_path(parts: Any) -> str:
    return "$" + "".join(f"[{p}]" if isinstance(p, int) else f".{p}" for p in parts)
