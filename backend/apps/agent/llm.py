"""Interfaz común de modelos de chat.

Cualquier modelo que cumpla `ChatModel` (texto de entrada, texto de salida) puede
usarse en el agente, sin depender de que soporte llamadas nativas a herramientas.
"""

from collections.abc import Callable
from typing import Literal, Protocol

from pydantic import BaseModel


class ChatMessage(BaseModel):
    role: Literal["system", "user", "assistant"]
    content: str


class ModelError(Exception):
    """El modelo no pudo responder (red, credenciales, modelo caído…)."""


class ChatModel(Protocol):
    name: str
    # Los modelos con `streams = True` aceptan `on_delta`, que recibe el texto acumulado.
    streams: bool

    def complete(
        self, messages: list[ChatMessage], on_delta: Callable[[str], None] | None = None
    ) -> str: ...
