"""Agente que resuelve una tarea llamando herramientas, con cualquier `ChatModel`.

Protocolo (igual para todos los modelos): en cada turno el modelo responde un único
objeto JSON, `{"tool": "<nombre>", "args": {...}}` para usar una herramienta, o
`{"final": "<respuesta>"}` para terminar.
"""

import json
from collections.abc import Callable, Sequence
from typing import Any

from pydantic import BaseModel, ConfigDict

from .llm import ChatMessage, ChatModel

DEFAULT_MAX_STEPS = 5


class Tool(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    name: str
    description: str
    run: Callable[..., Any]


class AgentStep(BaseModel):
    tool: str
    args: dict[str, Any]
    observation: str


class AgentResult(BaseModel):
    answer: str
    model: str
    steps: list[AgentStep]


class AgentError(Exception):
    """El agente no terminó dentro del número máximo de pasos."""


def run_agent(
    task: str,
    model: ChatModel,
    tools: Sequence[Tool],
    max_steps: int = DEFAULT_MAX_STEPS,
) -> AgentResult:
    tools_by_name = {tool.name: tool for tool in tools}
    messages = [
        ChatMessage(role="system", content=_system_prompt(tools)),
        ChatMessage(role="user", content=task),
    ]
    steps: list[AgentStep] = []

    for _ in range(max_steps):
        reply = model.complete(messages)
        messages.append(ChatMessage(role="assistant", content=reply))
        action = _parse_action(reply)

        if action is None:
            messages.append(
                ChatMessage(role="user", content="Respuesta no válida. Responde solo con JSON.")
            )
            continue
        if "final" in action:
            return AgentResult(answer=str(action["final"]), model=model.name, steps=steps)

        name = str(action.get("tool", ""))
        args = action.get("args", {})
        observation = _run_tool(tools_by_name, name, args)
        steps.append(
            AgentStep(
                tool=name, args=args if isinstance(args, dict) else {}, observation=observation
            )
        )
        messages.append(
            ChatMessage(
                role="user",
                content=(
                    f"Resultado de {name}: {observation}\n"
                    "Si ya tienes la respuesta final, responde solo con "
                    '{"final": "<respuesta>"}.'
                ),
            )
        )

    raise AgentError(f"El agente no terminó en {max_steps} pasos")


def _system_prompt(tools: Sequence[Tool]) -> str:
    lines = [f"- {tool.name}: {tool.description}" for tool in tools] or ["(sin herramientas)"]
    return (
        "Eres un agente que resuelve tareas de un flujo médico. Herramientas disponibles:\n"
        + "\n".join(lines)
        + "\n\nResponde SIEMPRE con un único objeto JSON y nada más:\n"
        '- para usar una herramienta: {"tool": "<nombre>", "args": {...}}\n'
        '- para terminar: {"final": "<respuesta>"}'
    )


def _parse_action(reply: str) -> dict[str, Any] | None:
    start, end = reply.find("{"), reply.rfind("}")
    if start == -1 or end <= start:
        return None
    try:
        action = json.loads(reply[start : end + 1])
    except json.JSONDecodeError:
        return None
    return action if isinstance(action, dict) else None


def _run_tool(tools_by_name: dict[str, Tool], name: str, args: Any) -> str:
    tool = tools_by_name.get(name)
    if tool is None:
        return f"Error: herramienta desconocida '{name}'"
    if not isinstance(args, dict):
        return "Error: 'args' debe ser un objeto JSON"
    try:
        result = tool.run(**args)
    except Exception as error:
        return f"Error: {error}"
    return (
        result if isinstance(result, str) else json.dumps(result, ensure_ascii=False, default=str)
    )
