"""Homologación de conceptos: unifica los términos de los profesionales en representantes comunes.

Un mismo concepto se dicta de muchas formas («VMI», «ventilación mecánica», «norepinefrina» /
«noradrenalina»). Para mantener un estándar de reportes, cada término de un registro se
reemplaza por su representante común:

1. Primero se busca en el diccionario (``data/conceptos.json`` más lo ya aprendido, en la
   tabla ``ConceptMapping``): es instantáneo.
2. Los términos desconocidos se le piden al modelo en una sola llamada (cacheada); lo que
   propone se guarda como mapeo *pendiente* para que una persona lo revise, y la próxima vez
   ya se resuelve sin modelo.
"""

import json
import logging
import re
import unicodedata
from collections.abc import Callable
from functools import cache
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from apps.agent.llm import ChatMessage

from . import extraction_services, pipeline_cache
from .models import Concept, ConceptMapping

logger = logging.getLogger(__name__)

SEED_PATH = Path(__file__).parent / "data" / "conceptos.json"
# Campos del registro cuyo valor es un término clínico homologable (el resto es texto libre).
HOMOLOGATED_KEYS = frozenset(
    {
        "farmaco",
        "principio_activo",
        "nombre",
        "tipo",
        "examen",
        "escala",
        "parametro",
        "soporte",
        "microorganismo",
        "muestra",
        "agente",
        "via",
    }
)
MAX_TERM_LENGTH = 60
# Metadatos y datos del propio profesional: no son conceptos clínicos.
SKIPPED_SECTIONS = frozenset({"metadatos"})

Progress = Callable[[list[dict[str, Any]]], None]


class Homologated(BaseModel):
    data: dict[str, Any]
    entries: list[dict[str, Any]]


def homologate(
    data: dict[str, Any], profession: str = "", on_progress: Progress | None = None
) -> Homologated:
    """Copia de ``data`` con los términos reemplazados por su representante común.

    ``entries`` describe cada término: sección, ruta, original, concepto, de dónde salió
    (``dictionary`` / ``model``) y si realmente cambió. ``on_progress`` recibe la lista
    parcial tras cada paso para poder mostrar cómo avanza.
    """
    ensure_seed()
    occurrences = _collect_terms(data)
    resolved = _known_concepts({normalize(o["original"]) for o in occurrences})

    entries = [_entry(o, resolved[normalize(o["original"])], "dictionary")
               for o in occurrences if normalize(o["original"]) in resolved]  # fmt: skip
    if entries and on_progress:
        on_progress(entries)

    unknown = sorted({normalize(o["original"]) for o in occurrences} - resolved.keys())
    if unknown:
        originals = {normalize(o["original"]): o["original"] for o in occurrences}
        proposals = _propose_concepts([originals[term] for term in unknown])
        resolved.update(_save_proposals(proposals, profession))

    entries = [_entry(o, resolved.get(normalize(o["original"])), _source(o, unknown, resolved))
               for o in occurrences]  # fmt: skip
    return Homologated(data=_apply(data, entries), entries=entries)


def list_mappings() -> list[ConceptMapping]:
    ensure_seed()
    mappings = ConceptMapping.objects.select_related("concept")
    return list(mappings.order_by("concept__canonical", "term"))


def normalize(term: str) -> str:
    """Clave para comparar términos: minúsculas, sin tildes y con «_» y espacios como uno solo."""
    decomposed = unicodedata.normalize("NFKD", term.strip().lower())
    plain = "".join(char for char in decomposed if not unicodedata.combining(char))
    return re.sub(r"[\s_]+", " ", plain)


def ensure_seed() -> None:
    """Carga el diccionario base la primera vez (idempotente)."""
    if ConceptMapping.objects.filter(source=ConceptMapping.Source.SEED).exists():
        return
    for canonical, info in _seed().items():
        concept, _ = Concept.objects.get_or_create(
            canonical=canonical, defaults={"category": info["category"]}
        )
        for alias in [canonical, *info["aliases"]]:
            ConceptMapping.objects.get_or_create(
                term=normalize(alias),
                defaults={
                    "original_term": alias,
                    "concept": concept,
                    "source": ConceptMapping.Source.SEED,
                    "status": ConceptMapping.Status.APPROVED,
                },
            )


@cache
def _seed() -> dict[str, dict[str, Any]]:
    return json.loads(SEED_PATH.read_text(encoding="utf-8"))


def _collect_terms(data: dict[str, Any]) -> list[dict[str, Any]]:
    """Ocurrencias de términos homologables: ``{section, path, key, original}``."""
    found: list[dict[str, Any]] = []

    def walk(node: Any, path: str, key: str, section: str) -> None:
        if isinstance(node, dict):
            for child_key, child in node.items():
                walk(child, f"{path}.{child_key}" if path else child_key, child_key, section)
        elif isinstance(node, list):
            for index, child in enumerate(node):
                walk(child, f"{path}[{index}]", key, section)
        elif isinstance(node, str) and key in HOMOLOGATED_KEYS and _is_term(node):
            found.append({"section": section, "path": path, "key": key, "original": node.strip()})

    for section, value in data.items():
        if section not in SKIPPED_SECTIONS:
            walk(value, section, section, section)
    return found


def _is_term(value: str) -> bool:
    return 0 < len(value.strip()) <= MAX_TERM_LENGTH


def _known_concepts(terms: set[str]) -> dict[str, str]:
    mappings = ConceptMapping.objects.filter(term__in=terms).select_related("concept")
    return {mapping.term: mapping.concept.canonical for mapping in mappings}


def _propose_concepts(terms: list[str]) -> dict[str, str]:
    """Concepto común propuesto por el modelo para cada término ({término: concepto})."""
    existing = list(Concept.objects.order_by("canonical").values_list("canonical", flat=True))
    key = pipeline_cache.cache_key(*terms)
    cached = pipeline_cache.load("homologation", key)
    if cached is not None:
        return {str(term): str(concept) for term, concept in cached.items()}

    messages = [
        ChatMessage(
            role="system",
            content=(
                "Eres un terminólogo clínico de una UCI chilena. Recibes términos que usaron "
                "distintos profesionales y debes unificarlos en un representante común.\n"
                "Para cada término responde el concepto estándar al que equivale: si uno de los "
                "conceptos existentes significa lo mismo, usa EXACTAMENTE ese texto; si no, "
                "propón el nombre estándar en español, completo y sin abreviaturas (siglas solo "
                "si son la forma habitual, p. ej. «Escala CPOT»), con la primera letra en "
                "mayúscula. Si el término ya es estándar, devuélvelo igual.\n"
                'Responde ÚNICAMENTE con JSON: {"conceptos": {"<término>": "<concepto>"}}.'
            ),
        ),
        ChatMessage(
            role="user",
            content=(
                f"Conceptos existentes:\n{json.dumps(existing, ensure_ascii=False)}\n\n"
                f"Términos a unificar:\n{json.dumps(terms, ensure_ascii=False)}"
            ),
        ),
    ]
    try:
        reply = extraction_services.complete_json(messages)
    except Exception:
        # Sin modelo no se bloquea el informe: los términos quedan tal cual.
        logger.exception("No se pudieron proponer conceptos; los términos quedan sin homologar")
        return {}
    raw = reply.get("conceptos")
    proposals = {
        term: str(raw[term]).strip()
        for term in terms
        if isinstance(raw, dict) and isinstance(raw.get(term), str) and raw[term].strip()
    }
    pipeline_cache.store("homologation", key, proposals)
    return proposals


def _save_proposals(proposals: dict[str, str], profession: str) -> dict[str, str]:
    """Guarda lo propuesto como mapeos pendientes y devuelve ``{término normalizado: concepto}``."""
    resolved: dict[str, str] = {}
    for original, canonical in proposals.items():
        concept, _ = Concept.objects.get_or_create(canonical=canonical)
        ConceptMapping.objects.get_or_create(
            term=normalize(original),
            defaults={
                "original_term": original,
                "concept": concept,
                "source": ConceptMapping.Source.MODEL,
                "status": ConceptMapping.Status.PENDING,
                "profession": profession,
            },
        )
        resolved[normalize(original)] = concept.canonical
    return resolved


def _source(occurrence: dict[str, Any], unknown: list[str], resolved: dict[str, str]) -> str:
    term = normalize(occurrence["original"])
    if term not in resolved:
        return "unresolved"
    return "model" if term in unknown else "dictionary"


def _entry(occurrence: dict[str, Any], canonical: str | None, source: str) -> dict[str, Any]:
    canonical = canonical or occurrence["original"]
    return {
        **occurrence,
        "canonical": canonical,
        "source": source,
        # Una diferencia solo de mayúsculas o tildes no es una homologación.
        "changed": normalize(canonical) != normalize(occurrence["original"]),
    }


def _apply(data: dict[str, Any], entries: list[dict[str, Any]]) -> dict[str, Any]:
    result = json.loads(json.dumps(data))
    for entry in entries:
        _set_path(result, entry["path"], entry["canonical"])
    return result


def _set_path(root: dict[str, Any], path: str, value: str) -> None:
    *parents, last = re.findall(r"[^.\[\]]+", path)
    node: Any = root
    for part in parents:
        node = node[int(part)] if isinstance(node, list) else node[part]
    if isinstance(node, list):
        node[int(last)] = value
    else:
        node[last] = value
