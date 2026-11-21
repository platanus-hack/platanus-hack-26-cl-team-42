"""Caché en disco de los pasos con modelo del pipeline (identificación, parseo, homologación).

Cada resultado se guarda como un JSON bajo ``samples/cache/<etapa>-<hash>.json``: repetir un
experimento con el mismo audio no vuelve a llamar al modelo. Los archivos se pueden versionar
para compartir las demos. ``PIPELINE_CACHE=false`` la desactiva y ``PIPELINE_CACHE_DIR`` cambia
la carpeta.
"""

import hashlib
import json
import logging
from pathlib import Path
from typing import Any

from decouple import config

logger = logging.getLogger(__name__)

DEFAULT_CACHE_DIR = Path(__file__).parent / "samples" / "cache"


def cache_key(*parts: str) -> str:
    return hashlib.sha256("\x00".join(parts).encode("utf-8")).hexdigest()


def load(stage: str, key: str) -> Any | None:
    if not _enabled():
        return None
    path = _path(stage, key)
    if not path.exists():
        return None
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        logger.warning("Caché ilegible: %s", path)
        return None
    logger.info("Etapa %s servida desde la caché", stage)
    return value


def store(stage: str, key: str, value: Any) -> None:
    if not _enabled():
        return
    path = _path(stage, key)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    except OSError:
        logger.warning("No se pudo guardar la caché: %s", path)


def _enabled() -> bool:
    return config("PIPELINE_CACHE", default=True, cast=bool)


def _path(stage: str, key: str) -> Path:
    directory = Path(config("PIPELINE_CACHE_DIR", default="") or DEFAULT_CACHE_DIR)
    return directory / f"{stage}-{key[:32]}.json"
