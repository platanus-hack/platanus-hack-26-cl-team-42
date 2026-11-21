"""Modelos disponibles para el agente. El modelo gratis (Qwen local) siempre está;
el endpoint de Hugging Face solo se activa si hay `HF_TOKEN`."""

import os
from functools import cache

from .llm import ChatModel, ModelError
from .providers import OpenAICompatibleChatModel, TransformersChatModel

DEFAULT_MODEL_NAME = "qwen-local"
# Modelo local de Hugging Face; se puede cambiar (p. ej. Qwen/Qwen2.5-7B-Instruct) con esta variable.
LOCAL_MODEL_ID = os.environ.get("QWEN_LOCAL_MODEL_ID", "Qwen/Qwen2.5-1.5B-Instruct")
# Los registros clínicos son JSON largos; la generación termina sola al cerrar la respuesta.
LOCAL_MAX_NEW_TOKENS = 4096
HF_ROUTER_URL = "https://router.huggingface.co/v1"
# Qwen3 Instruct responde directo con el JSON (sin bloque de razonamiento). Para más calidad:
# HF_MODEL_ID=Qwen/Qwen3-235B-A22B-Instruct-2507
HF_ROUTER_MODEL_ID = os.environ.get("HF_MODEL_ID") or "Qwen/Qwen3-30B-A3B-Instruct-2507"


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
        TransformersChatModel(
            DEFAULT_MODEL_NAME, model_id=LOCAL_MODEL_ID, max_new_tokens=LOCAL_MAX_NEW_TOKENS
        ),
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
