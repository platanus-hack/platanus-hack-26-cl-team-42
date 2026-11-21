"""Herramientas del proyecto que el agente puede usar. Cada módulo aporta las suyas."""

from apps.transcription.services import list_transcriptions

from .agent import Tool


def project_tools() -> list[Tool]:
    return [
        Tool(
            name="listar_transcripciones",
            description="Lista los audios transcritos con su texto y fecha de creación.",
            run=_listar_transcripciones,
        ),
    ]


def _listar_transcripciones() -> list[dict]:
    return [item.model_dump(mode="json") for item in list_transcriptions()]
