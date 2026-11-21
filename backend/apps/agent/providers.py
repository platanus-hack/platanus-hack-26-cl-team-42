"""Implementaciones concretas de `ChatModel`."""

from collections.abc import Callable
from functools import cache
from typing import Any

import requests

from .llm import ChatMessage, ModelError


class TransformersChatModel:
    """Modelo local con `transformers` (p. ej. Qwen). Gratis: no requiere token ni API."""

    streams = False

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

    streams = False

    def __init__(
        self,
        name: str,
        base_url: str,
        model_id: str,
        api_key: str,
        timeout: int = 180,
        max_tokens: int = 4096,
    ):
        self.name = name
        self.max_tokens = max_tokens
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
                    "max_tokens": self.max_tokens,
                },
                timeout=self.timeout,
            )
            response.raise_for_status()
            return str(response.json()["choices"][0]["message"]["content"])
        except (requests.RequestException, KeyError, IndexError, ValueError) as error:
            raise ModelError(f"{self.name}: {error}") from error


class AnthropicChatModel:
    """Claude por la API oficial de Anthropic."""

    FALLBACK_BETA = "server-side-fallback-2026-07-01"
    streams = True

    def __init__(
        self, name: str, model_id: str, api_key: str, max_tokens: int = 16000, timeout: int = 300
    ):
        import anthropic

        self.name = name
        self.model_id = model_id
        self.max_tokens = max_tokens
        self._errors = anthropic.APIError
        self._client = anthropic.Anthropic(api_key=api_key, timeout=timeout)

    def complete(
        self, messages: list[ChatMessage], on_delta: Callable[[str], None] | None = None
    ) -> str:
        system = "\n\n".join(message.content for message in messages if message.role == "system")
        chat = [message.model_dump() for message in messages if message.role != "system"]
        options: dict[str, Any] = {"system": system} if system else {}
        try:
            # Si un clasificador de seguridad rechaza la petición, la API reintenta en otro modelo.
            with self._client.beta.messages.stream(
                model=self.model_id,
                max_tokens=self.max_tokens,
                messages=chat,
                betas=[self.FALLBACK_BETA],
                fallbacks="default",
                **options,
            ) as stream:
                text = ""
                for chunk in stream.text_stream:
                    text += chunk
                    if on_delta:
                        on_delta(text)
                response = stream.get_final_message()
        except self._errors as error:
            raise ModelError(f"{self.name}: {error}") from error
        if response.stop_reason == "refusal":
            raise ModelError(f"{self.name}: el modelo rechazó la solicitud")
        return "".join(block.text for block in response.content if block.type == "text")


@cache
def _get_generator(model_id: str) -> Any:
    # Import diferido: transformers/torch son pesados y solo hacen falta al usar el modelo.
    from transformers import pipeline

    return pipeline("text-generation", model=model_id)
