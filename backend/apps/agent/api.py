"""Endpoints del agente, montados en `/-/api/agent/`."""

from ninja import Router, Schema
from ninja.errors import HttpError

from .agent import AgentError, AgentResult, run_agent
from .llm import ModelError
from .registry import DEFAULT_MODEL_NAME, UnknownModelError, available_models, get_chat_model
from .tools import project_tools

router = Router(tags=["agent"])


class RunAgentIn(Schema):
    task: str
    model: str | None = None


@router.get("/models", response=list[str])
def list_models(request):
    return available_models()


@router.post("/run", response=AgentResult)
def run(request, payload: RunAgentIn):
    try:
        model = get_chat_model(payload.model or DEFAULT_MODEL_NAME)
        return run_agent(payload.task, model, project_tools(request.user))
    except UnknownModelError as error:
        raise HttpError(404, str(error)) from error
    except AgentError as error:
        raise HttpError(422, str(error)) from error
    except ModelError as error:
        raise HttpError(502, str(error)) from error
