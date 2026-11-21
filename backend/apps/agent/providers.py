"""Implementaciones concretas de `ChatModel`."""

from functools import cache
from typing import Any

import requests

from .llm import ChatMessage, ModelError


class TransformersChatModel:
    """Modelo local con `transformers` (p. ej. Qwen). Gratis: no requiere token ni API."""

    def __init__(self, name: str, model_id: str, max_new_tokens: int = 512):
        self.name = name
        self.model_id = model_id
        self.max_new_tokens = max_new_tokens

    def complete(self, messages: list[ChatMessage]) -> str:
        generator = _get_generator(self.model_id)
        chat = [message.model_dump() for message in messages]
        try:
            output = generator(chat, max_new_tokens=self.max_new_tokens, do_sample=False)
        except Exception as error:
            raise ModelError(f"{self.name}: {error}") from error
        # Con entrada de chat, `generated_text` es la conversación completa; la última
        # entrada es la respuesta del asistente.
        return str(output[0]["generated_text"][-1]["content"])


class OpenAICompatibleChatModel:
    """Cualquier endpoint compatible con OpenAI (router de Hugging Face, Ollama, vLLM…)."""

    def __init__(self, name: str, base_url: str, model_id: str, api_key: str, timeout: int = 120):
        self.name = name
        self.base_url = base_url.rstrip("/")
        self.model_id = model_id
        self.api_key = api_key
        self.timeout = timeout

    def complete(self, messages: list[ChatMessage]) -> str:
        try:
            response = requests.post(
                f"{self.base_url}/chat/completions",
                headers={"Authorization": f"Bearer {self.api_key}"},
                json={
                    "model": self.model_id,
                    "messages": [message.model_dump() for message in messages],
                },
                timeout=self.timeout,
            )
            response.raise_for_status()
            return str(response.json()["choices"][0]["message"]["content"])
        except (requests.RequestException, KeyError, IndexError, ValueError) as error:
            raise ModelError(f"{self.name}: {error}") from error


@cache
def _get_generator(model_id: str) -> Any:
    # Import diferido: transformers/torch son pesados y solo hacen falta al usar el modelo.
    from transformers import pipeline

    return pipeline("text-generation", model=model_id)
