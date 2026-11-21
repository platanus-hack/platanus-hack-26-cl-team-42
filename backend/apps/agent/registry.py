"""Modelos disponibles para el agente. El modelo gratis (Qwen local) siempre está;
el endpoint de Hugging Face solo se activa si hay `HF_TOKEN`."""

import os
from functools import cache

from .llm import ChatModel, ModelError
from .providers import OpenAICompatibleChatModel, TransformersChatModel

DEFAULT_MODEL_NAME = "qwen-local"
HF_ROUTER_URL = "https://router.huggingface.co/v1"
HF_ROUTER_MODEL_ID = "Qwen/Qwen2.5-72B-Instruct"


class UnknownModelError(ModelError):
    pass


def available_models() -> list[str]:
    return list(_registry())


def get_chat_model(name: str) -> ChatModel:
    models = _registry()
    if name not in models:
        raise UnknownModelError(f"Modelo desconocido: {name}")
    return models[name]


@cache
def _registry() -> dict[str, ChatModel]:
    models: list[ChatModel] = [
        TransformersChatModel(DEFAULT_MODEL_NAME, model_id="Qwen/Qwen2.5-1.5B-Instruct"),
    ]
    hf_token = os.environ.get("HF_TOKEN", "")
    if hf_token:
        models.append(
            OpenAICompatibleChatModel(
                "qwen-hf",
                base_url=HF_ROUTER_URL,
                model_id=HF_ROUTER_MODEL_ID,
                api_key=hf_token,
            )
        )
    return {model.name: model for model in models}
