from unittest.mock import MagicMock, patch

import pytest
import requests
from django.contrib.auth import get_user_model
from django.test import Client

from apps.agent import providers, registry
from apps.agent.agent import AgentError, Tool, run_agent
from apps.agent.llm import ChatMessage, ModelError
from apps.agent.providers import OpenAICompatibleChatModel
from apps.agent.registry import DEFAULT_MODEL_NAME, UnknownModelError, get_chat_model


class ScriptedModel:
    """Modelo falso que responde con una lista fija de respuestas y guarda lo recibido."""

    def __init__(self, name: str, replies: list[str]):
        self.name = name
        self.replies = list(replies)
        self.received: list[list[ChatMessage]] = []

    def complete(self, messages: list[ChatMessage]) -> str:
        self.received.append(list(messages))
        return self.replies.pop(0)


def suma(a: int, b: int) -> int:
    return a + b


SUMA_TOOL = Tool(name="suma", description="Suma dos enteros.", run=suma)


def test_agent_returns_final_answer_without_tools():
    model = ScriptedModel("fake", ['{"final": "listo"}'])

    result = run_agent("hola", model, [SUMA_TOOL])

    assert result.answer == "listo"
    assert result.model == "fake"
    assert result.steps == []


def test_agent_runs_tool_and_feeds_observation_back():
    model = ScriptedModel(
        "fake",
        ['{"tool": "suma", "args": {"a": 2, "b": 3}}', '{"final": "5"}'],
    )

    result = run_agent("¿cuánto es 2+3?", model, [SUMA_TOOL])

    assert result.answer == "5"
    assert [(step.tool, step.observation) for step in result.steps] == [("suma", "5")]
    assert "Resultado de suma: 5" in model.received[1][-1].content


def test_agent_accepts_json_wrapped_in_prose():
    model = ScriptedModel("fake", ['Claro, aquí va: {"final": "ok"}. Gracias.'])

    assert run_agent("x", model, []).answer == "ok"


def test_agent_recovers_from_invalid_json_and_unknown_tool():
    model = ScriptedModel(
        "fake",
        ["no sé", '{"tool": "inexistente", "args": {}}', '{"final": "fin"}'],
    )

    result = run_agent("x", model, [SUMA_TOOL])

    assert result.answer == "fin"
    assert result.steps[0].observation == "Error: herramienta desconocida 'inexistente'"


def test_agent_reports_tool_exceptions_as_observations():
    model = ScriptedModel("fake", ['{"tool": "suma", "args": {"a": 1}}', '{"final": "x"}'])

    result = run_agent("x", model, [SUMA_TOOL])

    assert result.steps[0].observation.startswith("Error:")


def test_agent_raises_when_max_steps_exceeded():
    model = ScriptedModel("fake", ['{"tool": "suma", "args": {"a": 1, "b": 1}}'] * 3)

    with pytest.raises(AgentError):
        run_agent("x", model, [SUMA_TOOL], max_steps=3)


def test_openai_compatible_model_parses_reply():
    model = OpenAICompatibleChatModel("remoto", "https://example.test/v1/", "m", api_key="k")
    response = MagicMock()
    response.json.return_value = {"choices": [{"message": {"content": "hola"}}]}

    with patch.object(providers.requests, "post", return_value=response) as post:
        reply = model.complete([ChatMessage(role="user", content="hi")])

    assert reply == "hola"
    assert post.call_args.args[0] == "https://example.test/v1/chat/completions"
    assert post.call_args.kwargs["headers"] == {"Authorization": "Bearer k"}


def test_openai_compatible_model_wraps_http_errors():
    model = OpenAICompatibleChatModel("remoto", "https://example.test/v1", "m", api_key="bad")

    with patch.object(providers.requests, "post", side_effect=requests.ConnectionError("caído")):
        with pytest.raises(ModelError):
            model.complete([ChatMessage(role="user", content="hi")])


def test_registry_has_free_local_qwen_and_rejects_unknown_names(monkeypatch):
    monkeypatch.delenv("HF_TOKEN", raising=False)
    registry._registry.cache_clear()

    assert get_chat_model(DEFAULT_MODEL_NAME).name == DEFAULT_MODEL_NAME
    with pytest.raises(UnknownModelError):
        get_chat_model("no-existe")


@pytest.mark.django_db
def test_models_endpoint_lists_registered_models(settings):
    user = get_user_model().objects.create_user(email="agent@example.com", password="pw")
    client = Client()
    client.force_login(user)

    response = client.get(f"/{settings.URL_PREFIX}/api/agent/models")

    assert response.status_code == 200
    assert DEFAULT_MODEL_NAME in response.json()


@pytest.mark.django_db
def test_run_endpoint_uses_requested_model(settings):
    user = get_user_model().objects.create_user(email="agent2@example.com", password="pw")
    client = Client()
    client.force_login(user)
    fake = ScriptedModel("fake", ['{"final": "respuesta"}'])

    with patch("apps.agent.api.get_chat_model", return_value=fake) as get_model:
        response = client.post(
            f"/{settings.URL_PREFIX}/api/agent/run",
            {"task": "hola", "model": "fake"},
            content_type="application/json",
        )

    assert response.status_code == 200
    assert response.json()["answer"] == "respuesta"
    get_model.assert_called_once_with("fake")


@pytest.mark.django_db
def test_run_endpoint_returns_404_for_unknown_model(settings):
    user = get_user_model().objects.create_user(email="agent3@example.com", password="pw")
    client = Client()
    client.force_login(user)

    response = client.post(
        f"/{settings.URL_PREFIX}/api/agent/run",
        {"task": "hola", "model": "no-existe"},
        content_type="application/json",
    )

    assert response.status_code == 404


@pytest.mark.django_db
def test_project_tool_lists_transcriptions():
    from apps.agent.tools import project_tools

    [tool] = [t for t in project_tools() if t.name == "listar_transcripciones"]

    assert tool.run() == []
