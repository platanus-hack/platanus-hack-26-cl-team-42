"""Herramientas del proyecto que el agente puede usar. Cada módulo aporta las suyas.

Las herramientas se crean para un profesional concreto: el agente solo ve sus datos.
"""

from functools import partial
from typing import Any

from apps.transcription.services import list_transcriptions

from .agent import Tool


def project_tools(professional: Any) -> list[Tool]:
    return [
        Tool(
            name="listar_transcripciones",
            description="Lista los audios transcritos con su texto y fecha de creación.",
            run=partial(_listar_transcripciones, professional),
        ),
    ]


def _listar_transcripciones(professional: Any) -> list[dict]:
    return [item.model_dump(mode="json") for item in list_transcriptions(professional)]
