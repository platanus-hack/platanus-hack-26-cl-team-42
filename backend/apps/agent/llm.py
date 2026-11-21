"""Interfaz común de modelos de chat.

Cualquier modelo que cumpla `ChatModel` (texto de entrada, texto de salida) puede
usarse en el agente, sin depender de que soporte llamadas nativas a herramientas.
"""

from typing import Literal, Protocol

from pydantic import BaseModel


class ChatMessage(BaseModel):
    role: Literal["system", "user", "assistant"]
    content: str


class ModelError(Exception):
    """El modelo no pudo responder (red, credenciales, modelo caído…)."""


class ChatModel(Protocol):
    name: str

    def complete(self, messages: list[ChatMessage]) -> str: ...
